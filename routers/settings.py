"""
Configurações mutáveis em runtime.
GET  /settings  → retorna twitch_channel e youtube_channel_id atuais
POST /settings  → atualiza, salva em runtime_settings.json e aplica nos serviços
"""
import json
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from routers import chat as chat_router

FREE_CHANNEL_LIMIT = 2

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/channels", tags=["settings"])

SETTINGS_FILE = Path("runtime_settings.json")


class ChannelSettings(BaseModel):
    twitch_channel:     str  = ""
    youtube_channel_id: str  = ""
    kick_channel:       str  = ""
    chat_twitch:        bool = True
    chat_youtube:       bool = True
    chat_kick:          bool = True


def load_runtime_settings() -> ChannelSettings:
    """Carrega configurações salvas em runtime_settings.json."""
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return ChannelSettings(**data)
        except Exception as e:
            logger.warning(f"[Settings] Erro ao ler {SETTINGS_FILE}: {e}")
    return ChannelSettings()


def save_runtime_settings(s: ChannelSettings):
    """Salva configurações em runtime_settings.json."""
    SETTINGS_FILE.write_text(
        json.dumps(s.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


@router.get("", response_model=ChannelSettings)
async def get_settings(request: Request):
    """Retorna os canais configurados atualmente nos serviços em execução."""
    twitch  = getattr(request.app.state, "twitch",  None)
    youtube = getattr(request.app.state, "youtube", None)
    kick    = getattr(request.app.state, "kick",    None)
    return ChannelSettings(
        twitch_channel     = twitch.channel     if twitch  else "",
        youtube_channel_id = youtube.channel_id if youtube else "",
        kick_channel       = kick.channel        if kick    else "",
        chat_twitch        = chat_router._platform_enabled.get("twitch",  True),
        chat_youtube       = chat_router._platform_enabled.get("youtube", True),
        chat_kick          = chat_router._platform_enabled.get("kick",    True),
    )


@router.post("", response_model=ChannelSettings)
async def update_settings(body: ChannelSettings, request: Request):
    """
    Atualiza os canais em runtime e persiste em runtime_settings.json.
    Aplica imediatamente nos serviços sem reiniciar o servidor.
    """
    from routers.auth_supabase import _is_premium
    active = sum(1 for v in [body.chat_twitch, body.chat_youtube, body.chat_kick] if v)
    if not _is_premium and active > FREE_CHANNEL_LIMIT:
        raise HTTPException(status_code=403, detail="plan_limit")

    twitch  = getattr(request.app.state, "twitch",  None)
    youtube = getattr(request.app.state, "youtube", None)
    kick    = getattr(request.app.state, "kick",    None)

    if twitch and body.twitch_channel.strip():
        new_channel = body.twitch_channel.strip().lower().lstrip("#")
        if new_channel != twitch.channel:
            logger.info(f"[Settings] Twitch channel: '{twitch.channel}' → '{new_channel}'")
            twitch.stop_chat()
            twitch.channel = new_channel

    if youtube and body.youtube_channel_id.strip():
        new_id = body.youtube_channel_id.strip()
        if new_id != youtube.channel_id:
            logger.info(f"[Settings] YouTube channel ID: '{youtube.channel_id}' → '{new_id}'")
            youtube.stop_chat()
            youtube.channel_id   = new_id
            youtube._api_blocked = False   # reset para tentar com o novo canal

    if kick and body.kick_channel.strip():
        new_channel = body.kick_channel.strip().lower()
        if new_channel != kick.channel:
            logger.info(f"[Settings] Kick channel: '{kick.channel}' → '{new_channel}'")
            kick.stop_chat()
            kick.channel = new_channel

    # Apply chat platform toggles immediately
    chat_router.set_platform_enabled("twitch",  body.chat_twitch)
    chat_router.set_platform_enabled("youtube", body.chat_youtube)
    chat_router.set_platform_enabled("kick",    body.chat_kick)

    # Preserva canais existentes quando o body enviou string vazia
    # (postToggleSettings envia "" para plataformas desativadas — não deve apagar o canal salvo)
    current = load_runtime_settings()
    to_save = ChannelSettings(
        twitch_channel     = body.twitch_channel.strip()     or current.twitch_channel,
        youtube_channel_id = body.youtube_channel_id.strip() or current.youtube_channel_id,
        kick_channel       = body.kick_channel.strip()       or current.kick_channel,
        chat_twitch        = body.chat_twitch,
        chat_youtube       = body.chat_youtube,
        chat_kick          = body.chat_kick,
    )
    save_runtime_settings(to_save)
    logger.info(f"[Settings] Configurações salvas em {SETTINGS_FILE}")

    return body
