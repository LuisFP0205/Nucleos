"""
Nucleus Server
FastAPI application that powers:
  - Feature 12: Auto live-stream detection (Twitch + YouTube)
  - Feature 13: Windows media / music detection
  - Feature 14: Real-time chat via WebSocket

Run:
  pip install -r requirements.txt
  uvicorn main:app --host 0.0.0.0 --port 3000 --reload
"""
import asyncio
import logging
import os
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

# Quando empacotado com PyInstaller, garante que os caminhos relativos
# (static/, overlays/, Icones/, .env) resolvem a partir da pasta dos dados.
# sys._MEIPASS aponta para _internal/ onde o PyInstaller 6.x coloca os dados.
if getattr(sys, "frozen", False):
    # cwd = pasta do exe → arquivos do usuário (tokens, .env, runtime_settings)
    # ficam ao lado do Nucleus.exe, não dentro de _internal/
    _EXE_DIR = Path(sys.executable).parent
    os.chdir(_EXE_DIR)
    # console=False faz sys.stdout/stderr serem None — redireciona para devnull
    if sys.stdout is None:
        _devnull = open(os.devnull, "w")
        sys.stdout = _devnull
        sys.stderr = _devnull

import json
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse


# ------------------------------------------------------------------ #
# Overlay Event Manager — push de eventos (ex: tema alterado)          #
# ------------------------------------------------------------------ #

class _OverlayEventManager:
    def __init__(self):
        self._clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._clients:
            self._clients.remove(ws)

    async def broadcast(self, payload: dict):
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


overlay_events = _OverlayEventManager()

_VIEWERS_POS_FILE  = "overlay_viewers_positions.json"
_THEMES_FILE       = "overlay_themes.json"
_THEMES_DEFAULT    = {"chat": "minimal", "music": "minimal", "viewers": "minimal", "cam": "minimal", "countdown": "minimal"}

def _load_viewers_positions() -> dict:
    try:
        with open(_VIEWERS_POS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_viewers_positions(data: dict):
    with open(_VIEWERS_POS_FILE, "w") as f:
        json.dump(data, f)

def _load_themes() -> dict:
    try:
        with open(_THEMES_FILE, "r") as f:
            return {**_THEMES_DEFAULT, **json.load(f)}
    except Exception:
        return dict(_THEMES_DEFAULT)

def _save_themes(data: dict):
    with open(_THEMES_FILE, "w") as f:
        json.dump(data, f, indent=2)

from config import get_settings
from services.twitch_service import TwitchService
from services.youtube_service import YouTubeService
from services.kick_service import KickService
from services.obs_service import OBSService
from routers import stream as stream_router
from routers import music as music_router
from routers import chat as chat_router
from routers import auth as auth_router
from routers import settings as settings_router
from routers import keys as keys_router
from routers import logs as logs_router
from routers import auth_supabase as auth_supabase_router
from routers import obs as obs_router
from routers import countdown as countdown_router
from routers import custom_styles as custom_styles_router
from routers import custom_overlays as custom_overlays_router
from routers import analytics as analytics_router
from routers import commands as commands_router
from routers.chat import chat_manager
from routers.settings import load_runtime_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Suprime o WinError 10054 (cliente fechou conexão abruptamente) — falso positivo no Windows
class _SuppressConnectionReset(logging.Filter):
    def filter(self, record):
        return "WinError 10054" not in (record.getMessage())

logging.getLogger("asyncio").addFilter(_SuppressConnectionReset())

# Suprime endpoints de polling frequente dos logs de acesso do uvicorn
_SUPPRESS_PATHS = ("/music/current", "/stream/status")
class _SuppressPollingAccess(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        return not any(p in msg for p in _SUPPRESS_PATHS)

logging.getLogger("uvicorn.access").addFilter(_SuppressPollingAccess())


# ------------------------------------------------------------------ #
# App lifespan: start/stop background tasks                           #
# ------------------------------------------------------------------ #

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Carrega canais salvos pelo dashboard (runtime_settings.json),
    # usando os valores do .env como fallback
    rt = load_runtime_settings()
    twitch_channel     = rt.twitch_channel     or settings.twitch_channel
    youtube_channel_id = rt.youtube_channel_id or settings.youtube_channel_id
    kick_channel       = rt.kick_channel       or settings.kick_channel

    # Instantiate services
    twitch = TwitchService(
        client_id=settings.twitch_client_id,
        channel=twitch_channel,
        supabase_url=settings.supabase_url,
        supabase_anon_key=settings.supabase_anon_key,
    )
    # Estado de autenticação OAuth
    app.state.twitch_user_token    = None
    app.state.twitch_refresh_token = None
    app.state.twitch_login         = None
    app.state.youtube_access_token  = None
    app.state.youtube_refresh_token = None
    youtube = YouTubeService(
        channel_id=youtube_channel_id,
        supabase_url=settings.supabase_url,
        supabase_anon_key=settings.supabase_anon_key,
    )
    kick   = KickService(channel=kick_channel)
    app.state.kick_user_token = None
    obs    = OBSService(
        host=settings.obs_host,
        port=settings.obs_port,
        password=settings.obs_password,
    )

    logger.info(f"[Startup] Twitch channel: '{twitch_channel or '(não configurado)'}'")
    logger.info(f"[Startup] YouTube channel: '{youtube_channel_id or '(não configurado)'}'")
    logger.info(f"[Startup] Kick channel: '{kick_channel or '(não configurado)'}'")
    logger.info(f"[Startup] OBS WebSocket: ws://{settings.obs_host}:{settings.obs_port}")

    # Try to connect to OBS in the background (non-blocking — OBS may not be open)
    asyncio.create_task(obs.connect())

    # Apply saved chat platform toggles
    chat_router.set_platform_enabled("twitch",  rt.chat_twitch)
    chat_router.set_platform_enabled("youtube", rt.chat_youtube)
    chat_router.set_platform_enabled("kick",    rt.chat_kick)

    # ── Restaura tokens OAuth salvos (reconexão automática) ──────────────
    try:
        from services.token_store import load_all as _load_tokens
        _saved = _load_tokens()

        tw = _saved.get("twitch")
        if tw and tw.get("access_token"):
            app.state.twitch_user_token    = tw["access_token"]
            app.state.twitch_refresh_token = tw.get("refresh_token", "")
            app.state.twitch_login         = tw.get("login", "")
            twitch.set_user_token(tw["access_token"], tw.get("login", ""))
            logger.info(f"[Startup] Twitch token restaurado para '{tw.get('login', '?')}'")

        yt = _saved.get("youtube")
        if yt and yt.get("access_token"):
            youtube.set_oauth_token(yt["access_token"])
            if yt.get("channel_id") and not youtube_channel_id:
                youtube.channel_id = yt["channel_id"]
            app.state.youtube_access_token  = yt["access_token"]
            app.state.youtube_refresh_token = yt.get("refresh_token", "")
            logger.info(f"[Startup] YouTube token restaurado para '{yt.get('channel_name', '?')}'")

        ki = _saved.get("kick")
        if ki and ki.get("access_token"):
            kick.set_user_token(ki["access_token"])
            app.state.kick_user_token = ki["access_token"]
            if ki.get("username") and not kick.channel:
                kick.channel = ki["username"].lower()
            logger.info(f"[Startup] Kick token restaurado para '{ki.get('username', '?')}'")


    except Exception as e:
        logger.warning(f"[Startup] Falha ao restaurar tokens: {e}")

    # Wire command system
    commands_router.set_services(twitch=twitch, youtube=youtube, kick=kick)
    chat_router.set_command_handler(commands_router.process_message)

    # Store on app state for access in routes
    app.state.twitch  = twitch
    app.state.youtube = youtube
    app.state.kick    = kick
    app.state.obs     = obs

    # ── Refresh automático de tokens (YouTube 50min, Twitch 30d, Kick on-demand) ─
    from services.token_refresh import start_refresh_loop
    refresh_task = asyncio.create_task(start_refresh_loop(app))

    # Start the live-stream auto-detection loop
    detection_task = asyncio.create_task(
        stream_router.detection_loop(
            twitch_svc=twitch,
            youtube_svc=youtube,
            kick_svc=kick,
            chat_manager=chat_manager,
            obs_svc=obs,
            interval=settings.stream_check_interval,
        )
    )
    logger.info(
        f"[Startup] Stream detection loop started (interval={settings.stream_check_interval}s)"
    )

    url = f"http://{settings.host if settings.host != '0.0.0.0' else 'localhost'}:{settings.port}"
    logger.info(f"[Startup] Dashboard: {url}")

    yield  # Application runs here

    # Cleanup
    detection_task.cancel()
    refresh_task.cancel()
    twitch.stop_chat()
    youtube.stop_chat()
    kick.stop_chat()
    await obs.disconnect()
    logger.info("[Shutdown] Background tasks stopped")


# ------------------------------------------------------------------ #
# FastAPI app                                                          #
# ------------------------------------------------------------------ #

app = FastAPI(
    title="Nucleus",
    description="Live stream overlay & chat server",
    version="1.0.0",
    lifespan=lifespan,
)

# Routers
app.include_router(stream_router.router)
app.include_router(music_router.router)
app.include_router(chat_router.router)
app.include_router(auth_router.router)
app.include_router(settings_router.router)
app.include_router(keys_router.router)
app.include_router(logs_router.router)
app.include_router(auth_supabase_router.router)
app.include_router(obs_router.router)
app.include_router(countdown_router.router)
app.include_router(custom_styles_router.router)
app.include_router(custom_overlays_router.router)
app.include_router(analytics_router.router)
app.include_router(commands_router.router, prefix="/api")

# Static files — quando empacotado, buscados dentro de _internal/ (_MEIPASS)
_ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
app.mount("/static",   StaticFiles(directory=str(_ASSETS / "static")),   name="static")
app.mount("/overlays", StaticFiles(directory=str(_ASSETS / "overlays")), name="overlays")
app.mount("/icones",   StaticFiles(directory=str(_ASSETS / "Icones")),   name="icones")


# ------------------------------------------------------------------ #
# Convenience redirects                                               #
# ------------------------------------------------------------------ #

@app.get("/debug/yt/chat", include_in_schema=False)
async def debug_yt_chat(request: Request):
    """Testa direto o endpoint liveChat/messages e mostra o resultado bruto."""
    import httpx as _httpx
    svc = getattr(request.app.state, "youtube", None)
    if not svc:
        return JSONResponse({"error": "YouTubeService não inicializado"})

    live_chat_id = svc._live_chat_id
    if not live_chat_id:
        return JSONResponse({"error": "live_chat_id não definido — live não detectada ainda"})

    headers = {}
    params  = {"part": "id,snippet,authorDetails", "liveChatId": live_chat_id, "maxResults": 5}

    if svc._oauth_token:
        headers["Authorization"] = f"Bearer {svc._oauth_token}"
    else:
        params["key"] = svc.api_key

    try:
        async with _httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/youtube/v3/liveChat/messages",
                params=params, headers=headers, timeout=10,
            )
        return JSONResponse({
            "status":        resp.status_code,
            "using_oauth":   bool(svc._oauth_token),
            "live_chat_id":  live_chat_id,
            "body":          resp.json(),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)})


@app.get("/debug/twitch", include_in_schema=False)
async def debug_twitch(request: Request):
    """Diagnóstico rápido da Twitch — estado do IRC e token."""
    import httpx as _httpx
    svc   = getattr(request.app.state, "twitch", None)
    token = getattr(request.app.state, "twitch_user_token", None)
    login = getattr(request.app.state, "twitch_login", None)

    result = {
        "token_present":    bool(token),
        "login":            login,
        "channel":          svc.channel if svc else "N/A",
        "irc_connected":    svc.chat_connected if svc else False,
        "ws_open":          bool(svc._ws) if svc else False,
    }

    # Valida token na API da Twitch
    if token:
        try:
            async with _httpx.AsyncClient() as client:
                r = await client.get(
                    "https://id.twitch.tv/oauth2/validate",
                    headers={"Authorization": f"OAuth {token}"},
                    timeout=8,
                )
                result["validate_status"] = r.status_code
                if r.status_code == 200:
                    data = r.json()
                    result["validate_login"]      = data.get("login")
                    result["validate_expires_in"] = data.get("expires_in")
                    result["validate_scopes"]     = data.get("scopes")
                else:
                    result["validate_body"] = r.text[:200]
        except Exception as e:
            result["validate_error"] = str(e)
    else:
        result["validate_skip"] = "sem token OAuth"

    return JSONResponse(result)


@app.get("/debug/yt", include_in_schema=False)
async def debug_yt(request: Request):
    """Diagnóstico rápido do YouTube — acesse no browser para ver o estado."""
    import httpx as _httpx
    yt  = getattr(request.app.state, "yt_token_ok", None)
    svc = getattr(request.app.state, "youtube", None)
    tok = getattr(request.app.state, "youtube_access_token", None)

    result = {
        "oauth_token_in_state": bool(tok),
        "oauth_token_in_service": bool(svc._oauth_token if svc else None),
        "channel_id": svc.channel_id if svc else "N/A",
        "chat_connected": svc.chat_connected if svc else False,
        "api_blocked": svc._api_blocked if svc else False,
        "live_chat_id": svc._live_chat_id if svc else None,
    }

    # Testa chamada live ao YouTube
    if svc and svc._oauth_token:
        try:
            async with _httpx.AsyncClient() as client:
                r = await client.get(
                    "https://www.googleapis.com/youtube/v3/liveBroadcasts",
                    params={"part": "id,snippet,status", "broadcastStatus": "active",
                            "broadcastType": "all", "mine": "true"},
                    headers={"Authorization": f"Bearer {svc._oauth_token}"},
                    timeout=8,
                )
                result["liveBroadcasts_status"] = r.status_code
                result["liveBroadcasts_body"]   = r.json()
        except Exception as e:
            result["liveBroadcasts_error"] = str(e)
    else:
        result["liveBroadcasts_skip"] = "sem OAuth token"

    return JSONResponse(result)


@app.get("/", include_in_schema=False)
async def root():
    return FileResponse(str(_ASSETS / "static" / "dashboard.html"))


@app.get("/previews", include_in_schema=False)
async def previews():
    return FileResponse(str(_ASSETS / "static" / "previews.html"))


@app.get("/plans", include_in_schema=False)
async def plans_page():
    return FileResponse(str(_ASSETS / "static" / "plans.html"))


@app.get("/themes", include_in_schema=False)
async def themes_page():
    return FileResponse(str(_ASSETS / "static" / "themes.html"))



@app.get("/connections", include_in_schema=False)
async def connections_page():
    return FileResponse(str(_ASSETS / "static" / "connections.html"))


@app.get("/overlays", include_in_schema=False)
async def overlays_page():
    return FileResponse(str(_ASSETS / "static" / "overlays.html"))


@app.get("/chat", include_in_schema=False)
async def chat_page():
    return FileResponse(str(_ASSETS / "static" / "chat.html"))


@app.get("/music", include_in_schema=False)
async def music_page():
    return FileResponse(str(_ASSETS / "static" / "music_page.html"))


@app.get("/settings", include_in_schema=False)
async def settings_page():
    return FileResponse(str(_ASSETS / "static" / "settings.html"))


@app.get("/guide", include_in_schema=False)
async def guide_page():
    return FileResponse(str(_ASSETS / "static" / "guide.html"))


@app.get("/logs", include_in_schema=False)
async def logs_page():
    return FileResponse(str(_ASSETS / "static" / "logs.html"))


@app.get("/overlay/chat", include_in_schema=False)
async def overlay_chat():
    content = open(_ASSETS / "overlays" / "chat.html", "rb").read()
    return Response(content=content, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/overlay/music", include_in_schema=False)
async def overlay_music():
    content = open(_ASSETS / "overlays" / "music.html", "rb").read()
    return Response(content=content, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/overlay/viewers", include_in_schema=False)
async def overlay_viewers():
    content = open(_ASSETS / "overlays" / "viewers.html", "rb").read()
    return Response(content=content, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/overlay/cam", include_in_schema=False)
async def overlay_cam():
    content = open(_ASSETS / "overlays" / "cam.html", "rb").read()
    return Response(content=content, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/overlay/countdown", include_in_schema=False)
async def overlay_countdown():
    content = open(_ASSETS / "overlays" / "countdown.html", "rb").read()
    return Response(content=content, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/overlay-editor", include_in_schema=False)
async def overlay_editor():
    content = open(_ASSETS / "static" / "overlay-editor.html", "rb").read()
    return Response(content=content, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/commands", include_in_schema=False)
async def commands_page():
    content = open(_ASSETS / "static" / "commands.html", "rb").read()
    return Response(content=content, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/analytics", include_in_schema=False)
async def analytics_page():
    content = open(_ASSETS / "static" / "analytics.html", "rb").read()
    return Response(content=content, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/overlay/viewers/positions", include_in_schema=False)
async def get_viewers_positions():
    return JSONResponse(_load_viewers_positions())


@app.post("/overlay/viewers/positions", include_in_schema=False)
async def save_viewers_positions(request: Request):
    data = await request.json()
    _save_viewers_positions(data)
    return JSONResponse({"ok": True})


@app.get("/overlay/themes", include_in_schema=False)
async def get_overlay_themes():
    return JSONResponse(_load_themes())


@app.post("/overlay/themes", include_in_schema=False)
async def save_overlay_themes(request: Request):
    data = await request.json()
    current = _load_themes()
    for k in ("chat", "music", "viewers", "cam", "countdown"):
        if k in data:
            current[k] = data[k]
    _save_themes(current)
    # Notifica todos os overlays conectados para aplicar o novo tema
    asyncio.create_task(overlay_events.broadcast({
        "type": "theme_changed",
        "themes": current,
    }))
    return JSONResponse({"ok": True})


@app.websocket("/ws/overlay-events")
async def ws_overlay_events(ws: WebSocket):
    await overlay_events.connect(ws)
    try:
        while True:
            await ws.receive_text()  # mantém conexão aberta
    except (WebSocketDisconnect, Exception):
        overlay_events.disconnect(ws)


# ------------------------------------------------------------------ #
# Convenience API aliases for the new UI                              #
# ------------------------------------------------------------------ #

@app.get("/auth/me", include_in_schema=False)
async def auth_me(request: Request):
    """Returns the current Supabase user info (email, plan)."""
    from routers.auth_supabase import _current_user, _is_premium
    if _current_user:
        return JSONResponse({
            "email": _current_user.get("email", ""),
            "plan_type": "premium" if _is_premium else "free",
            "display_name": (_current_user.get("user_metadata") or {}).get("display_name", ""),
        })
    return JSONResponse({"email": "", "plan_type": "free", "display_name": ""})


@app.get("/api/settings", include_in_schema=False)
async def api_get_settings(request: Request):
    """Alias: returns runtime settings + env-based keys for the settings UI."""
    from routers.settings import load_runtime_settings
    from config import get_settings as _cfg
    cfg = _cfg()
    rs = load_runtime_settings()
    return JSONResponse({
        "twitch_channel":      rs.twitch_channel,
        "youtube_channel_id":  rs.youtube_channel_id,
        "kick_channel":        rs.kick_channel,
        # Keys (masked — only show if set, otherwise empty)
        "twitch_client_id":  "••••••" if cfg.twitch_client_id else "",
        "google_client_id":  "••••••" if cfg.google_client_id else "",
        "kick_client_id":    "••••••" if cfg.kick_client_id else "",
        "supabase_url":      "••••••" if cfg.supabase_url else "",
        "supabase_anon_key": "••••••" if cfg.supabase_anon_key else "",
    })


@app.post("/api/settings", include_in_schema=False)
async def api_post_settings(request: Request):
    """Saves runtime settings (channels, OBS config, etc.) to runtime_settings.json."""
    from routers.settings import load_runtime_settings, save_runtime_settings, ChannelSettings
    data = await request.json()
    current = load_runtime_settings()
    updated = ChannelSettings(
        twitch_channel     = data.get("twitch_channel",     current.twitch_channel),
        youtube_channel_id = data.get("youtube_channel_id", current.youtube_channel_id),
        kick_channel       = data.get("kick_channel",       current.kick_channel),
        chat_twitch        = data.get("platform_twitch",    current.chat_twitch),
        chat_youtube       = data.get("platform_youtube",   current.chat_youtube),
        chat_kick          = data.get("platform_kick",      current.chat_kick),
    )
    save_runtime_settings(updated)
    return JSONResponse({"ok": True})


@app.get("/api/logs", include_in_schema=False)
async def api_get_logs(lines: int = 100):
    """Returns last N log lines from the in-memory log history."""
    from routers.logs import _history
    all_lines = list(_history)
    return JSONResponse({"lines": all_lines[-lines:]})


if __name__ == "__main__":
    import time
    import uvicorn
    settings = get_settings()
    frozen = getattr(sys, "frozen", False)
    url = f"http://localhost:{settings.port}"

    if frozen:
        # Executável: uvicorn em thread daemon + janela pywebview na thread principal
        import socket
        import webview

        # Espera a porta estar livre antes de iniciar (cobre restart e reabertura rápida)
        for _ in range(20):
            try:
                with socket.create_connection(("localhost", settings.port), timeout=0.3):
                    time.sleep(0.3)  # porta ainda ocupada
            except OSError:
                break  # porta livre — pode iniciar

        def _run_server():
            uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)

        threading.Thread(target=_run_server, daemon=True).start()

        # Aguarda o servidor estar realmente disponível (até 15s)
        for _ in range(30):
            time.sleep(0.5)
            try:
                with socket.create_connection(("localhost", settings.port), timeout=0.3):
                    break
            except OSError:
                pass
        time.sleep(0.5)

        # Usa --restart-url se vier de um restart, senão abre o dashboard
        restart_url = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--restart-url=")), None)
        open_url = f"http://localhost:{settings.port}{restart_url}" if restart_url else url

        # Pasta persistente para cookies/localStorage (sessão Supabase)
        _wv_storage = Path.home() / "AppData" / "Local" / "Nucleus" / "webview"
        _wv_storage.mkdir(parents=True, exist_ok=True)

        window = webview.create_window(
            "Nucleus",
            open_url,
            width=1280,
            height=800,
            min_size=(900, 600),
        )
        webview.start(storage_path=str(_wv_storage), private_mode=False)
        os._exit(0)
    else:
        # Desenvolvimento: abre browser e roda uvicorn com reload
        if "--no-browser" not in sys.argv:
            threading.Timer(1.5, webbrowser.open, args=[url]).start()
        uvicorn.run(
            "main:app",
            host=settings.host,
            port=settings.port,
            reload=True,
            reload_dirs=["routers", "services", "models"],  # só observa código Python
        )
