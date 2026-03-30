"""
Analytics — records viewer counts and timeline events during streams.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

_VIEWERS_FILE = Path("analytics_viewers.json")
_EVENTS_FILE  = Path("analytics_events.json")

_MAX_HOURS   = 48          # keep up to 48h of data
_MAX_SAMPLES = _MAX_HOURS * 120   # ~every 30s → 2/min → 120/h
_MAX_EVENTS  = 500

_viewers: list[dict] = []
_events:  list[dict] = []

# ── Persistence ──────────────────────────────────────────────────

def _load() -> None:
    global _viewers, _events
    if _VIEWERS_FILE.exists():
        try:
            _viewers = json.loads(_VIEWERS_FILE.read_text("utf-8"))
        except Exception:
            _viewers = []
    if _EVENTS_FILE.exists():
        try:
            _events = json.loads(_EVENTS_FILE.read_text("utf-8"))
        except Exception:
            _events = []


def _flush_viewers() -> None:
    _VIEWERS_FILE.write_text(
        json.dumps(_viewers[-_MAX_SAMPLES:], ensure_ascii=False), "utf-8"
    )


def _flush_events() -> None:
    _EVENTS_FILE.write_text(
        json.dumps(_events[-_MAX_EVENTS:], ensure_ascii=False), "utf-8"
    )


# ── Public helpers (called by stream.py) ─────────────────────────

def record_viewers(tw: int, yt: int, kick: int) -> None:
    """Record a viewer snapshot. Called from detection_loop every cycle."""
    total = tw + yt + kick
    now   = int(time.time())

    snap = {"ts": now, "tw": tw, "yt": yt, "kick": kick, "total": total}
    _viewers.append(snap)

    # Prune old data
    cutoff = now - _MAX_HOURS * 3600
    while _viewers and _viewers[0]["ts"] < cutoff:
        _viewers.pop(0)

    _flush_viewers()

    # Auto-detect new all-time peak (within current data window)
    if total > 0 and _viewers:
        hist_peak = max(v["total"] for v in _viewers)
        prev_peaks = [e for e in _events if e["type"] == "peak"]
        prev_peak_val = prev_peaks[-1]["value"] if prev_peaks else 0
        if total == hist_peak and total > prev_peak_val:
            add_event("peak", f"Novo pico: {total} viewers", total)

    # Viewer milestones (fire once each)
    for m in (10, 25, 50, 100, 200, 500, 1000, 2000, 5000):
        if total >= m:
            if not any(e["type"] == "milestone" and e["value"] == m for e in _events):
                add_event("milestone", f"✦ {m} viewers atingidos!", m)


def add_event(event_type: str, label: str, value=None) -> None:
    """Append a timeline event."""
    _events.append({
        "ts":    int(time.time()),
        "type":  event_type,
        "label": label,
        "value": value,
    })
    _flush_events()


# ── API Endpoints ─────────────────────────────────────────────────

@router.get("/analytics/viewers", include_in_schema=False)
async def api_viewers(hours: int = 2):
    cutoff = int(time.time()) - max(1, min(hours, 48)) * 3600
    return JSONResponse([v for v in _viewers if v["ts"] >= cutoff])


@router.get("/analytics/events", include_in_schema=False)
async def api_events(limit: int = 100):
    return JSONResponse(_events[-limit:])


@router.get("/analytics/summary", include_in_schema=False)
async def api_summary():
    now = int(time.time())
    window_1h = [v for v in _viewers if v["ts"] >= now - 3600]
    window_all = _viewers

    current = window_all[-1]["total"]  if window_all else 0
    peak    = max((v["total"] for v in window_all), default=0)
    avg_1h  = int(sum(v["total"] for v in window_1h) / len(window_1h)) if window_1h else 0

    # Stream duration from last stream_start event
    duration_s = 0
    start_evs = [e for e in _events if e["type"] == "stream_start"]
    if start_evs:
        last_start = start_evs[-1]["ts"]
        end_evs = [e for e in _events if e["type"] == "stream_end" and e["ts"] > last_start]
        duration_s = (end_evs[-1]["ts"] if end_evs else now) - last_start

    # Platform breakdown (last known snapshot)
    last = window_all[-1] if window_all else {"tw": 0, "yt": 0, "kick": 0}

    return JSONResponse({
        "current":    current,
        "peak":       peak,
        "avg_1h":     avg_1h,
        "duration_s": duration_s,
        "tw":         last.get("tw",   0),
        "yt":         last.get("yt",   0),
        "kick":       last.get("kick", 0),
        "samples":    len(window_all),
    })


@router.delete("/analytics/clear", include_in_schema=False)
async def api_clear():
    global _viewers, _events
    _viewers.clear()
    _events.clear()
    _flush_viewers()
    _flush_events()
    return JSONResponse({"ok": True})


_load()
