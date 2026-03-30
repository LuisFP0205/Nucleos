"""
Commands — chat command system.

Built-in: !uptime, !song, !clip
Custom:   user-defined triggers with variable substitution

Variables in custom responses:
  {user}      → username who sent the command
  {platform}  → twitch / youtube / kick
  {viewers}   → current total viewers
  {uptime}    → stream uptime (HH:MM or Xh Ym)
  {game}      → current Twitch game (Twitch only)
  {song}      → current song title – artist
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Optional, Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi import Request

logger = logging.getLogger(__name__)
router = APIRouter()

_COMMANDS_FILE = Path("commands.json")

# ── Default built-in commands ─────────────────────────────────────
_BUILTINS: list[dict] = [
    {
        "id": "uptime", "trigger": "!uptime", "response": None,
        "enabled": True, "cooldown": 10, "builtin": True,
        "description": "Tempo de live", "uses": 0,
    },
    {
        "id": "song", "trigger": "!song", "response": None,
        "enabled": True, "cooldown": 5, "builtin": True,
        "description": "Música tocando agora", "uses": 0,
    },
    {
        "id": "clip", "trigger": "!clip", "response": None,
        "enabled": True, "cooldown": 30, "builtin": True,
        "description": "Criar clip (Twitch)", "uses": 0,
    },
]

_builtins_state: dict[str, dict] = {}   # id → {enabled, cooldown, uses}
_custom: list[dict]               = []
_last_used: dict[str, float]      = {}  # command_id → last trigger timestamp

# ── Service references (set from main.py) ────────────────────────
_twitch_svc  = None
_youtube_svc = None
_kick_svc    = None


def set_services(twitch, youtube, kick=None) -> None:
    global _twitch_svc, _youtube_svc, _kick_svc
    _twitch_svc  = twitch
    _youtube_svc = youtube
    _kick_svc    = kick


# ── Persistence ──────────────────────────────────────────────────

def _load() -> None:
    global _custom, _builtins_state
    if not _COMMANDS_FILE.exists():
        _builtins_state = {b["id"]: {"enabled": b["enabled"], "cooldown": b["cooldown"], "uses": 0}
                           for b in _BUILTINS}
        return
    try:
        data = json.loads(_COMMANDS_FILE.read_text("utf-8"))
        _builtins_state = data.get("builtins", {})
        # Ensure all builtins are represented
        for b in _BUILTINS:
            if b["id"] not in _builtins_state:
                _builtins_state[b["id"]] = {"enabled": True, "cooldown": b["cooldown"], "uses": 0}
        _custom = data.get("custom", [])
    except Exception as e:
        logger.warning(f"[Commands] Falha ao carregar: {e}")
        _builtins_state = {b["id"]: {"enabled": True, "cooldown": b["cooldown"], "uses": 0}
                           for b in _BUILTINS}


def _flush() -> None:
    try:
        _COMMANDS_FILE.write_text(
            json.dumps({"builtins": _builtins_state, "custom": _custom}, ensure_ascii=False, indent=2),
            "utf-8"
        )
    except Exception as e:
        logger.warning(f"[Commands] Falha ao salvar: {e}")


# ── Helpers ──────────────────────────────────────────────────────

def _all_commands() -> list[dict]:
    """Return merged list of built-ins + custom for API responses."""
    result = []
    for b in _BUILTINS:
        state = _builtins_state.get(b["id"], {})
        result.append({**b, "enabled": state.get("enabled", True),
                       "cooldown": state.get("cooldown", b["cooldown"]),
                       "uses": state.get("uses", 0)})
    result.extend(_custom)
    return result


def _is_on_cooldown(cmd_id: str, cooldown: int) -> bool:
    return (time.time() - _last_used.get(cmd_id, 0)) < cooldown


def _mark_used(cmd_id: str) -> None:
    _last_used[cmd_id] = time.time()
    # Increment use counter
    if cmd_id in _builtins_state:
        _builtins_state[cmd_id]["uses"] = _builtins_state[cmd_id].get("uses", 0) + 1
    else:
        for c in _custom:
            if c["id"] == cmd_id:
                c["uses"] = c.get("uses", 0) + 1
                break
    _flush()


def _fmt_uptime(seconds: int) -> str:
    if seconds <= 0:
        return "0m"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


async def _resolve_uptime() -> str:
    """Try to get stream uptime from analytics events."""
    try:
        from routers import analytics as _an
        events = _an._events
        starts = [e for e in events if e["type"] == "stream_start"]
        if starts:
            elapsed = int(time.time()) - starts[-1]["ts"]
            return _fmt_uptime(max(0, elapsed))
    except Exception:
        pass
    return "desconhecido"


async def _resolve_viewers() -> int:
    try:
        from routers import analytics as _an
        if _an._viewers:
            return _an._viewers[-1].get("total", 0)
    except Exception:
        pass
    return 0


async def _resolve_song() -> str:
    try:
        from services.music_service import MusicService
        info = await MusicService.get_current()
        if info and info.get("title"):
            artist = info.get("artist", "")
            return f"{info['title']}{' – ' + artist if artist else ''}"
    except Exception:
        pass
    return "Nenhuma música tocando"


async def _substitute(template: str, user: str, platform: str) -> str:
    """Replace variables in a custom command response."""
    result = template
    result = result.replace("{user}", user)
    result = result.replace("{platform}", platform)
    if "{viewers}" in result:
        result = result.replace("{viewers}", str(await _resolve_viewers()))
    if "{uptime}" in result:
        result = result.replace("{uptime}", await _resolve_uptime())
    if "{song}" in result:
        result = result.replace("{song}", await _resolve_song())
    return result


# ── Command processor (called from chat.py hook) ─────────────────

async def process_message(msg: dict) -> None:
    """
    Called for every chat message. Detects commands and sends responses
    back to the originating platform.
    """
    text     = (msg.get("message") or "").strip()
    platform = msg.get("platform", "")
    user     = msg.get("user", "")

    if not text.startswith("!"):
        return

    trigger = text.split()[0].lower()

    # ── Check built-ins ──────────────────────────────────────────
    for b in _BUILTINS:
        state = _builtins_state.get(b["id"], {})
        if not state.get("enabled", True):
            continue
        if b["trigger"] != trigger:
            continue
        cooldown = state.get("cooldown", b["cooldown"])
        if _is_on_cooldown(b["id"], cooldown):
            return
        _mark_used(b["id"])

        response = await _run_builtin(b["id"], user, platform, text)
        if response:
            await _send_response(platform, response)
        return

    # ── Check custom commands ────────────────────────────────────
    for c in _custom:
        if not c.get("enabled", True):
            continue
        if c.get("trigger", "").lower() != trigger:
            continue
        cooldown = c.get("cooldown", 5)
        if _is_on_cooldown(c["id"], cooldown):
            return
        _mark_used(c["id"])

        response = await _substitute(c.get("response", ""), user, platform)
        if response:
            await _send_response(platform, response)
        return


async def _run_builtin(cmd_id: str, user: str, platform: str, raw_text: str) -> Optional[str]:
    if cmd_id == "uptime":
        uptime = await _resolve_uptime()
        return f"A live está no ar há {uptime}"

    if cmd_id == "song":
        song = await _resolve_song()
        return f"🎵 {song}"

    if cmd_id == "clip":
        if platform != "twitch":
            return "Clips só estão disponíveis no Twitch!"
        if _twitch_svc is None:
            return None
        url = await _twitch_svc.create_clip()
        if url:
            return f"✂️ Clip criado: {url}"
        return "Não foi possível criar o clip (verifique o token OAuth)."

    return None


async def _send_response(platform: str, text: str) -> None:
    """Send a text response to the correct platform chat."""
    try:
        if platform == "twitch" and _twitch_svc:
            ok = await _twitch_svc.send_message(text)
            if ok:
                logger.info(f"[Commands] Twitch → {text[:60]}")
            else:
                logger.debug("[Commands] Twitch send_message retornou False (sem token?)")

        elif platform == "youtube" and _youtube_svc:
            ok = await _youtube_svc.send_message(text)
            if ok:
                logger.info(f"[Commands] YouTube → {text[:60]}")
            else:
                logger.debug("[Commands] YouTube send_message retornou False (sem OAuth?)")

        elif platform == "kick" and _kick_svc:
            ok = await _kick_svc.send_message(text)
            if ok:
                logger.info(f"[Commands] Kick → {text[:60]}")
            else:
                logger.debug("[Commands] Kick send_message retornou False (sem token OAuth?)")

    except Exception as e:
        logger.warning(f"[Commands] Erro ao enviar resposta ({platform}): {e}")


# ── API Endpoints ────────────────────────────────────────────────

@router.get("/commands", include_in_schema=False)
async def list_commands():
    return JSONResponse(_all_commands())


@router.post("/commands", include_in_schema=False)
async def create_command(request: Request):
    body = await request.json()
    trigger = (body.get("trigger") or "").strip().lower()
    if not trigger.startswith("!"):
        trigger = "!" + trigger
    response = (body.get("response") or "").strip()
    if not trigger or not response:
        return JSONResponse({"error": "trigger e response são obrigatórios"}, status_code=400)

    # Prevent duplicate triggers
    all_triggers = [b["trigger"] for b in _BUILTINS] + [c["trigger"] for c in _custom]
    if trigger in all_triggers:
        return JSONResponse({"error": "Trigger já existe"}, status_code=409)

    cmd = {
        "id":          str(uuid.uuid4()),
        "trigger":     trigger,
        "response":    response,
        "enabled":     True,
        "cooldown":    int(body.get("cooldown", 5)),
        "builtin":     False,
        "description": body.get("description", ""),
        "uses":        0,
    }
    _custom.append(cmd)
    _flush()
    return JSONResponse(cmd, status_code=201)


@router.put("/commands/{cmd_id}", include_in_schema=False)
async def update_command(cmd_id: str, request: Request):
    body = await request.json()

    # Built-in: only allow toggling enabled/cooldown
    if cmd_id in _builtins_state:
        if "enabled" in body:
            _builtins_state[cmd_id]["enabled"] = bool(body["enabled"])
        if "cooldown" in body:
            _builtins_state[cmd_id]["cooldown"] = int(body["cooldown"])
        _flush()
        return JSONResponse({"ok": True})

    # Custom
    for c in _custom:
        if c["id"] == cmd_id:
            if "trigger" in body:
                new_trigger = body["trigger"].strip().lower()
                if not new_trigger.startswith("!"):
                    new_trigger = "!" + new_trigger
                c["trigger"] = new_trigger
            if "response"    in body: c["response"]    = body["response"]
            if "enabled"     in body: c["enabled"]     = bool(body["enabled"])
            if "cooldown"    in body: c["cooldown"]    = int(body["cooldown"])
            if "description" in body: c["description"] = body["description"]
            _flush()
            return JSONResponse(c)

    return JSONResponse({"error": "Comando não encontrado"}, status_code=404)


@router.patch("/commands/{cmd_id}/toggle", include_in_schema=False)
async def toggle_command(cmd_id: str):
    if cmd_id in _builtins_state:
        _builtins_state[cmd_id]["enabled"] = not _builtins_state[cmd_id].get("enabled", True)
        _flush()
        return JSONResponse({"enabled": _builtins_state[cmd_id]["enabled"]})

    for c in _custom:
        if c["id"] == cmd_id:
            c["enabled"] = not c.get("enabled", True)
            _flush()
            return JSONResponse({"enabled": c["enabled"]})

    return JSONResponse({"error": "Não encontrado"}, status_code=404)


@router.delete("/commands/{cmd_id}", include_in_schema=False)
async def delete_command(cmd_id: str):
    global _custom
    if cmd_id in _builtins_state:
        return JSONResponse({"error": "Comandos built-in não podem ser deletados"}, status_code=400)
    _custom = [c for c in _custom if c["id"] != cmd_id]
    _flush()
    return JSONResponse({"ok": True})


_load()
