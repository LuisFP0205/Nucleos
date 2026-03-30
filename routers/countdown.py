"""
Countdown / Timer overlay — integrado com troca de cena OBS.

POST /countdown/start   → inicia countdown { duration, target_scene, message }
POST /countdown/stop    → para e reseta
POST /countdown/pause   → pausa (mantém tempo restante)
POST /countdown/resume  → retoma de onde parou
GET  /countdown/state   → estado atual
WS   /ws/countdown      → push em tempo real (1 msg/s enquanto rodando)
"""
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter(tags=["countdown"])

# ── Estado ────────────────────────────────────────────────────────────────────

_state: dict = {
    "running":      False,
    "paused":       False,
    "duration":     0,
    "remaining":    0,
    "target_scene": "",
    "message":      "",
    "finished":     False,
}
_obs_svc = None
_task: Optional[asyncio.Task] = None
_clients: list = []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _snapshot() -> dict:
    rem = max(0, _state["remaining"])
    return {
        **_state,
        "remaining": rem,
        "display":   f"{rem // 60:02d}:{rem % 60:02d}",
    }


async def _broadcast(payload: dict):
    dead = []
    for ws in list(_clients):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _clients:
            _clients.remove(ws)


# ── Background loop ───────────────────────────────────────────────────────────

async def _run_countdown():
    global _state
    while True:
        await asyncio.sleep(1)

        if not _state["running"] or _state["paused"]:
            continue

        _state["remaining"] = max(0, _state["remaining"] - 1)
        await _broadcast(_snapshot())

        if _state["remaining"] == 0:
            _state["running"]  = False
            _state["finished"] = True
            await _broadcast(_snapshot())

            # Auto-switch OBS scene
            target = _state.get("target_scene", "")
            if target and _obs_svc and _obs_svc.is_connected:
                try:
                    await _obs_svc.set_scene(target)
                    logger.info(f"[Countdown] Cena OBS trocada → '{target}'")
                except Exception as e:
                    logger.warning(f"[Countdown] Falha ao trocar cena OBS: {e}")
            break


def _ensure_task():
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_run_countdown())


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/countdown/start")
async def countdown_start(request: Request):
    global _state, _obs_svc

    body = await request.json()
    duration     = max(1, int(body.get("duration", 300)))
    target_scene = str(body.get("target_scene", "")).strip()
    message      = str(body.get("message", "")).strip()

    _obs_svc = getattr(request.app.state, "obs", None)

    # Cancela loop anterior se estiver rodando
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(_task), timeout=0.5)
        except Exception:
            pass

    _state = {
        "running":      True,
        "paused":       False,
        "duration":     duration,
        "remaining":    duration,
        "target_scene": target_scene,
        "message":      message,
        "finished":     False,
    }
    _ensure_task()
    await _broadcast(_snapshot())
    return {"ok": True, **_snapshot()}


@router.post("/countdown/stop")
async def countdown_stop():
    global _state, _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(_task), timeout=0.5)
        except Exception:
            pass
    _state = {**_state, "running": False, "paused": False,
               "finished": False, "remaining": _state["duration"]}
    await _broadcast(_snapshot())
    return {"ok": True, **_snapshot()}


@router.post("/countdown/pause")
async def countdown_pause():
    if _state["running"]:
        _state["paused"] = not _state["paused"]
        await _broadcast(_snapshot())
    return {"ok": True, **_snapshot()}


@router.get("/countdown/state")
async def countdown_state():
    return _snapshot()


@router.websocket("/ws/countdown")
async def ws_countdown(ws: WebSocket):
    await ws.accept()
    _clients.append(ws)
    try:
        await ws.send_json(_snapshot())
        while True:
            await ws.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        if ws in _clients:
            _clients.remove(ws)
