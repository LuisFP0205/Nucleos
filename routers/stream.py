"""
Feature 12 – Auto-detection of active live streams.
GET /stream/status      →  { youtube_live, twitch_live, kick_live, ... }
GET /stream/detect-now  →  força checagem imediata (sem esperar 30s)
WS  /ws/status          →  push em tempo real ao detectar mudança de status
"""
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from models.schemas import StreamStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/stream", tags=["stream"])

# Shared state (populated by the background detector in main.py)
_status = StreamStatus()
_force_event: Optional[asyncio.Event] = None


# ------------------------------------------------------------------ #
# StatusManager — push WebSocket para o dashboard                     #
# ------------------------------------------------------------------ #

class StatusManager:
    def __init__(self):
        self._clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.append(ws)
        logger.info(f"[WS/status] Client connected (total={len(self._clients)})")
        # Envia o status atual ao conectar
        try:
            await ws.send_json(_status.model_dump())
        except Exception:
            pass

    def disconnect(self, ws: WebSocket):
        if ws in self._clients:
            self._clients.remove(ws)
        logger.info(f"[WS/status] Client disconnected (total={len(self._clients)})")

    async def broadcast(self, status: StreamStatus):
        payload = status.model_dump()
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


status_manager = StatusManager()


@router.websocket("/ws/status")
async def websocket_status(ws: WebSocket):
    await status_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()   # mantém a conexão aberta
    except WebSocketDisconnect:
        status_manager.disconnect(ws)
    except Exception:
        status_manager.disconnect(ws)


def get_status() -> StreamStatus:
    return _status


def update_status(new: StreamStatus):
    global _status
    _status = new


@router.get("/status", response_model=StreamStatus)
async def stream_status():
    """Return current live status for all configured platforms."""
    return _status



@router.post("/detect-now")
async def detect_now(request: Request):
    """Força uma checagem de live imediata sem esperar o intervalo de 30s."""
    global _force_event
    if _force_event:
        _force_event.set()
    twitch_svc  = getattr(request.app.state, "twitch",   None)
    youtube_svc = getattr(request.app.state, "youtube",  None)
    kick_svc    = getattr(request.app.state, "kick",     None)
    return {
        "ok": True,
        "twitch_channel":  twitch_svc.channel     if twitch_svc  else None,
        "youtube_channel": youtube_svc.channel_id  if youtube_svc else None,
        "kick_channel":    kick_svc.channel        if kick_svc    else None,
        "current_status":  _status,
    }


# ------------------------------------------------------------------ #
# Background auto-detection loop (started from main.py)              #
# ------------------------------------------------------------------ #

async def detection_loop(twitch_svc, youtube_svc, kick_svc, chat_manager, obs_svc=None, interval: int = 30):
    from routers.chat import broadcast as _filtered_broadcast, _platform_enabled
    """
    Runs every `interval` seconds (or immediately via /stream/detect-now).
    Detects active streams and auto-starts chat listeners.
    """
    global _force_event
    _force_event = asyncio.Event()

    prev_twitch   = False
    prev_youtube  = False
    prev_kick     = False
    prev_any_live = False

    while True:
        new_status = StreamStatus()

        # --- Twitch ---
        if _platform_enabled.get("twitch", True):
            try:
                info = await twitch_svc.get_stream_info()
                if info:
                    new_status.twitch_live       = True
                    new_status.twitch_stream_id  = info["id"]
                    new_status.twitch_viewers    = info.get("viewer_count", 0)
                    new_status.twitch_live_since = info.get("started_at")
                    new_status.twitch_title      = info.get("title")
                    new_status.twitch_game       = info.get("game_name")
                    new_status.twitch_channel    = twitch_svc.channel
                    if not prev_twitch:
                        logger.info(f"[AutoDetect] Twitch live detectada: {info['title']}")
                    if not twitch_svc.chat_connected:
                        twitch_svc.start_chat(_filtered_broadcast)
                else:
                    if prev_twitch:
                        logger.info("[AutoDetect] Twitch stream encerrada")
                        twitch_svc.stop_chat()
            except Exception as e:
                logger.error(f"[AutoDetect] Twitch error: {e}")
        elif prev_twitch:
            twitch_svc.stop_chat()

        # --- YouTube ---
        if _platform_enabled.get("youtube", True):
            try:
                info = await youtube_svc.get_active_live()
                if info:
                    new_status.youtube_live         = True
                    new_status.youtube_video_id     = info["video_id"]
                    new_status.youtube_live_chat_id = info["live_chat_id"]
                    new_status.youtube_viewers      = info.get("viewers", 0)
                    new_status.youtube_live_since   = info.get("started_at")
                    new_status.youtube_title        = info.get("title")
                    new_status.youtube_stream_id    = info["video_id"]
                    if not prev_youtube:
                        logger.info(f"[AutoDetect] YouTube live detectada: {info['title']}")
                    if info.get("live_chat_id") and not youtube_svc.chat_connected:
                        logger.info(f"[AutoDetect] Iniciando chat YouTube (liveChatId={info['live_chat_id']})")
                        youtube_svc.start_chat(info["live_chat_id"], _filtered_broadcast)
                else:
                    if prev_youtube:
                        logger.info("[AutoDetect] YouTube stream encerrada")
                        youtube_svc.stop_chat()
            except Exception as e:
                logger.error(f"[AutoDetect] YouTube error: {e}")
        elif prev_youtube:
            youtube_svc.stop_chat()

        # --- Kick ---
        if _platform_enabled.get("kick", True):
            try:
                info = await kick_svc.get_stream_info()
                if info:
                    new_status.kick_live       = True
                    new_status.kick_stream_id  = info["id"]
                    new_status.kick_viewers    = info.get("viewer_count", 0)
                    new_status.kick_live_since = info.get("started_at")
                    new_status.kick_title      = info.get("title")
                    new_status.kick_channel    = kick_svc.channel
                    if not prev_kick:
                        logger.info(f"[AutoDetect] Kick live detectada: {info['title']}")
                    if info.get("chatroom_id") and not kick_svc.chat_connected:
                        logger.info(f"[AutoDetect] Iniciando chat Kick (chatroom_id={info['chatroom_id']})")
                        kick_svc.start_chat(info["chatroom_id"], _filtered_broadcast)
                else:
                    if prev_kick:
                        logger.info("[AutoDetect] Kick stream encerrada")
                        kick_svc.stop_chat()
            except Exception as e:
                logger.error(f"[AutoDetect] Kick error: {e}")
        elif prev_kick:
            kick_svc.stop_chat()

        # Detecta mudança antes de sobrescrever o estado anterior
        old = _status
        changed = (
            new_status.twitch_live     != old.twitch_live     or
            new_status.youtube_live    != old.youtube_live    or
            new_status.kick_live       != old.kick_live       or
            new_status.twitch_viewers  != old.twitch_viewers  or
            new_status.youtube_viewers != old.youtube_viewers or
            new_status.kick_viewers    != old.kick_viewers
        )

        update_status(new_status)

        if changed and status_manager._clients:
            asyncio.create_task(status_manager.broadcast(new_status))

        prev_twitch  = new_status.twitch_live
        prev_youtube = new_status.youtube_live
        prev_kick    = new_status.kick_live

        # OBS auto-switch: muda cena quando o estado live/offline muda
        new_any_live = new_status.twitch_live or new_status.youtube_live or new_status.kick_live
        if obs_svc and obs_svc.is_connected and new_any_live != prev_any_live:
            from routers.obs import _auto_switch_cfg
            cfg = _auto_switch_cfg
            if cfg.get("enabled"):
                target = cfg.get("live_scene") if new_any_live else cfg.get("offline_scene")
                if target:
                    logger.info(f"[OBS AutoSwitch] {'Live' if new_any_live else 'Offline'} → cena '{target}'")
                    asyncio.create_task(obs_svc.set_scene(target))
        # Analytics: stream start / end events (must run before prev_any_live is updated)
        try:
            from routers import analytics as _analytics
            if new_any_live and not prev_any_live:
                platforms = []
                if new_status.twitch_live:  platforms.append("Twitch")
                if new_status.youtube_live: platforms.append("YouTube")
                if new_status.kick_live:    platforms.append("Kick")
                _analytics.add_event("stream_start",
                    f"Stream iniciou ({', '.join(platforms)})")
            elif not new_any_live and prev_any_live:
                _analytics.add_event("stream_end", "Stream encerrou")
        except Exception:
            pass

        prev_any_live = new_any_live

        # Analytics: record viewer snapshot (only while live)
        if new_any_live:
            try:
                from routers import analytics as _analytics
                _analytics.record_viewers(
                    new_status.twitch_viewers  or 0,
                    new_status.youtube_viewers or 0,
                    new_status.kick_viewers    or 0,
                )
            except Exception:
                pass

        # Aguarda o intervalo OU um sinal de /detect-now
        try:
            await asyncio.wait_for(_force_event.wait(), timeout=interval)
            _force_event.clear()
            logger.info("[AutoDetect] Checagem forçada por /stream/detect-now")
        except asyncio.TimeoutError:
            pass  # intervalo normal expirou
