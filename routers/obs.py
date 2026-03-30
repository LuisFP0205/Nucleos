"""
OBS WebSocket integration router.

GET  /obs/status              → connection + current scene + streaming/recording
POST /obs/connect             → (re)connect to OBS
POST /obs/disconnect          → disconnect from OBS
GET  /obs/scenes              → list of all scenes
POST /obs/scene               → switch scene  { "scene": "Scene Name" }
GET  /obs/sources             → sources in a scene  ?scene=Name (defaults to current)
POST /obs/source/visible      → toggle source visibility  { "scene", "source", "visible" }
GET  /obs/auto-switch         → get auto-switch config
POST /obs/auto-switch         → save auto-switch config  { "enabled", "live_scene", "offline_scene" }
"""
import json
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/obs", tags=["obs"])

_AUTO_SWITCH_FILE = "obs_auto_switch.json"
_auto_switch_cfg: dict = {
    "enabled":       False,
    "live_scene":    "",
    "offline_scene": "",
}


def load_auto_switch() -> dict:
    global _auto_switch_cfg
    try:
        with open(_AUTO_SWITCH_FILE) as f:
            _auto_switch_cfg = {**_auto_switch_cfg, **json.load(f)}
    except Exception:
        pass
    return _auto_switch_cfg


def save_auto_switch(cfg: dict):
    global _auto_switch_cfg
    _auto_switch_cfg = cfg
    try:
        with open(_AUTO_SWITCH_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        logger.warning(f"[OBS] Could not save auto-switch config: {e}")


# Load on module import
load_auto_switch()


def _obs(request: Request):
    return getattr(request.app.state, "obs", None)


# ------------------------------------------------------------------ #
# Connection                                                           #
# ------------------------------------------------------------------ #

@router.get("/status")
async def obs_status(request: Request):
    svc = _obs(request)
    if not svc:
        return JSONResponse({"connected": False, "error": "OBS service not initialized"})
    return JSONResponse(await svc.get_status())


@router.post("/connect")
async def obs_connect(request: Request):
    svc = _obs(request)
    if not svc:
        return JSONResponse({"ok": False, "error": "OBS service not initialized"})
    ok = await svc.connect()
    if ok:
        status = await svc.get_status()
        return JSONResponse({"ok": True, **status})
    return JSONResponse({"ok": False, "error": "Could not connect. Check host/port/password."})


@router.post("/disconnect")
async def obs_disconnect(request: Request):
    svc = _obs(request)
    if svc:
        await svc.disconnect()
    return JSONResponse({"ok": True})


# ------------------------------------------------------------------ #
# Scenes                                                               #
# ------------------------------------------------------------------ #

@router.get("/scenes")
async def obs_scenes(request: Request):
    svc = _obs(request)
    if not svc:
        return JSONResponse([])
    status = await svc.get_status()
    return JSONResponse(status.get("scenes", []))


@router.post("/scene")
async def obs_set_scene(request: Request):
    svc = _obs(request)
    if not svc:
        return JSONResponse({"ok": False, "error": "OBS service not initialized"})
    body = await request.json()
    scene = body.get("scene", "").strip()
    if not scene:
        return JSONResponse({"ok": False, "error": "scene required"}, status_code=400)
    ok = await svc.set_scene(scene)
    return JSONResponse({"ok": ok})


# ------------------------------------------------------------------ #
# Sources                                                              #
# ------------------------------------------------------------------ #

@router.get("/sources")
async def obs_sources(request: Request, scene: str = ""):
    svc = _obs(request)
    if not svc:
        return JSONResponse([])
    if not scene:
        status = await svc.get_status()
        scene = status.get("current_scene", "")
    if not scene:
        return JSONResponse([])
    sources = await svc.get_sources(scene)
    return JSONResponse(sources)


@router.post("/source/visible")
async def obs_source_visible(request: Request):
    svc = _obs(request)
    if not svc:
        return JSONResponse({"ok": False, "error": "OBS service not initialized"})
    body = await request.json()
    ok = await svc.set_source_visible(
        body.get("scene", ""),
        body.get("source", ""),
        bool(body.get("visible", True)),
    )
    return JSONResponse({"ok": ok})


# ------------------------------------------------------------------ #
# Auto-switch config                                                   #
# ------------------------------------------------------------------ #

@router.get("/auto-switch")
async def obs_get_auto_switch():
    return JSONResponse(_auto_switch_cfg)


@router.post("/auto-switch")
async def obs_set_auto_switch(request: Request):
    body = await request.json()
    cfg = {
        "enabled":       bool(body.get("enabled", False)),
        "live_scene":    str(body.get("live_scene", "")).strip(),
        "offline_scene": str(body.get("offline_scene", "")).strip(),
    }
    save_auto_switch(cfg)
    return JSONResponse({"ok": True, "config": cfg})
