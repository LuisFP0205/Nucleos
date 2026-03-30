"""
Custom Overlays — user-defined HTML+CSS overlays with injected system JS.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter()

_DB = Path("overlay_custom_layouts.json")


def _load() -> list:
    if _DB.exists():
        try:
            return json.loads(_DB.read_text("utf-8"))
        except Exception:
            return []
    return []


def _save(data: list) -> None:
    _DB.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")


_DEFAULT_HTML = """\
<div class="ov-root">

  <!-- ── Chat ─────────────────────────────────────────────── -->
  <div data-nucleus="chat"
       data-max-messages="25"
       data-timeout="30000"
       class="chat-list">
  </div>

</div>"""

_DEFAULT_CSS = """\
/* ── Layout ─────────────────────────────────────────────────── */
.ov-root {
  position: absolute;
  inset: 0;
  padding: 16px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 6px;
}

/* ── Chat list ───────────────────────────────────────────────── */
.chat-list {
  display: flex;
  flex-direction: column-reverse;
  gap: 5px;
  overflow: hidden;
}

/* ── Message rows (added by Nucleus Runtime) ─────────────────── */
.nucleus-msg {
  background: rgba(0, 0, 0, 0.72);
  backdrop-filter: blur(4px);
  border-radius: 8px;
  padding: 6px 12px;
  font-family: 'Segoe UI', Arial, sans-serif;
  font-size: 14px;
  color: #efeff1;
  animation: slideIn .2s ease;
  border-left: 3px solid rgba(0, 200, 224, .5);
}

.nucleus-user {
  font-weight: 700;
}

.nucleus-text {
  opacity: .92;
}

@keyframes slideIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}"""


def _render_overlay(ov: dict, base_url: str) -> str:
    safe_name = ov.get("name", "Overlay").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>{safe_name}</title>
<style>
*, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: transparent; width: 100vw; height: 100vh; overflow: hidden; position: relative; }}
{ov.get("css", "")}
</style>
</head>
<body>
{ov.get("html", "")}
<script>window.__NUCLEUS_BASE__ = "{base_url}";</script>
<script src="{base_url}/static/nucleus-runtime.js"></script>
</body>
</html>"""


@router.get("/overlay/custom-list", include_in_schema=False)
async def list_custom_overlays():
    return JSONResponse(_load())


@router.post("/overlay/custom-new", include_in_schema=False)
async def create_custom_overlay(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    items = _load()
    entry: dict = {
        "id":         str(uuid.uuid4())[:8],
        "name":       (data.get("name") or "Meu Overlay").strip(),
        "html":       data.get("html", _DEFAULT_HTML),
        "css":        data.get("css",  _DEFAULT_CSS),
        "created_at": datetime.now().isoformat(),
    }
    items.append(entry)
    _save(items)
    return JSONResponse(entry)


@router.put("/overlay/custom-update/{ov_id}", include_in_schema=False)
async def update_custom_overlay(ov_id: str, request: Request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    items = _load()
    for ov in items:
        if ov["id"] == ov_id:
            for key in ("name", "html", "css"):
                if key in data:
                    ov[key] = data[key]
            ov["updated_at"] = datetime.now().isoformat()
            _save(items)
            return JSONResponse(ov)
    raise HTTPException(status_code=404, detail="Not found")


@router.delete("/overlay/custom-delete/{ov_id}", include_in_schema=False)
async def delete_custom_overlay(ov_id: str):
    items = _load()
    items = [o for o in items if o["id"] != ov_id]
    _save(items)
    return JSONResponse({"ok": True})


@router.get("/overlay/custom/{ov_id}", include_in_schema=False)
async def serve_custom_overlay(ov_id: str, request: Request):
    items = _load()
    for ov in items:
        if ov["id"] == ov_id:
            base = str(request.base_url).rstrip("/")
            return HTMLResponse(
                _render_overlay(ov, base),
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
    raise HTTPException(status_code=404, detail="Overlay não encontrado")
