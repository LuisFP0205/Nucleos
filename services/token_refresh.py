"""
Token Refresh Service — renova automaticamente os OAuth tokens antes de expirarem.

YouTube: expira em 1h    → renova a cada 50 min
Twitch:  expira em ~60d  → renova a cada 30 dias + valida no startup
Kick:    indefinido (beta) → valida no startup, renova se a API retornar 401
"""
import asyncio
import logging
import httpx
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

YOUTUBE_REFRESH_INTERVAL = 50 * 60        # 50 minutos
TWITCH_REFRESH_INTERVAL  = 30 * 24 * 3600 # 30 dias
TWITCH_VALIDATE_URL      = "https://id.twitch.tv/oauth2/validate"
TWITCH_TOKEN_URL         = "https://id.twitch.tv/oauth2/token"
GOOGLE_TOKEN_URL         = "https://oauth2.googleapis.com/token"


# ── YouTube ────────────────────────────────────────────────────────────────────

async def refresh_youtube(app: "FastAPI") -> bool:
    """Renova o access_token do YouTube usando o refresh_token salvo."""
    refresh_token        = getattr(app.state, "youtube_refresh_token", None)
    google_client_id     = _get_setting(app, "google_client_id")
    google_client_secret = _get_setting(app, "google_client_secret")

    if not refresh_token or not google_client_id or not google_client_secret:
        logger.debug("[TokenRefresh] YouTube: refresh_token ou credenciais ausentes")
        return False

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id":     google_client_id,
                    "client_secret": google_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type":    "refresh_token",
                },
            )
            if resp.status_code != 200:
                logger.warning(f"[TokenRefresh] YouTube falhou: {resp.status_code} {resp.text[:200]}")
                return False

            new_token = resp.json().get("access_token", "")
            if not new_token:
                return False

        # Atualiza app.state
        app.state.youtube_access_token = new_token
        yt_svc = getattr(app.state, "youtube", None)
        if yt_svc:
            yt_svc.set_oauth_token(new_token)

        # Atualiza token_store mantendo o refresh_token
        from services.token_store import load_token, save_token
        saved = load_token("youtube") or {}
        saved["access_token"] = new_token
        save_token("youtube", saved)

        logger.info("[TokenRefresh] YouTube access_token renovado")
        return True

    except Exception as e:
        logger.warning(f"[TokenRefresh] YouTube erro: {e}")
        return False


# ── Twitch ─────────────────────────────────────────────────────────────────────

async def validate_twitch(app: "FastAPI") -> bool:
    """Valida o token Twitch atual. Retorna True se válido."""
    token = getattr(app.state, "twitch_user_token", None)
    if not token:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                TWITCH_VALIDATE_URL,
                headers={"Authorization": f"OAuth {token}"},
                timeout=10,
            )
            if resp.status_code == 200:
                data  = resp.json()
                login = data.get("login", "")
                # Atualiza login se mudou
                if login:
                    app.state.twitch_login = login
                    tw_svc = getattr(app.state, "twitch", None)
                    if tw_svc:
                        tw_svc._user_nick = login
                logger.info(f"[TokenRefresh] Twitch token válido para '{login}'")
                return True
            return False
    except Exception as e:
        logger.warning(f"[TokenRefresh] Twitch validate erro: {e}")
        return False


async def refresh_twitch(app: "FastAPI") -> bool:
    """Renova o access_token da Twitch usando o refresh_token."""
    refresh_token  = getattr(app.state, "twitch_refresh_token", None)
    client_id      = _get_setting(app, "twitch_client_id")
    client_secret  = _get_setting(app, "twitch_client_secret")

    if not refresh_token or not client_id or not client_secret:
        logger.debug("[TokenRefresh] Twitch: refresh_token ou credenciais ausentes")
        return False

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                TWITCH_TOKEN_URL,
                params={
                    "client_id":     client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type":    "refresh_token",
                },
            )
            if resp.status_code != 200:
                logger.warning(f"[TokenRefresh] Twitch falhou: {resp.status_code} {resp.text[:200]}")
                return False

            data          = resp.json()
            new_token     = data.get("access_token", "")
            new_refresh   = data.get("refresh_token", refresh_token)
            if not new_token:
                return False

        # Atualiza app.state
        app.state.twitch_user_token    = new_token
        app.state.twitch_refresh_token = new_refresh
        tw_svc = getattr(app.state, "twitch", None)
        if tw_svc:
            tw_svc.set_user_token(new_token, app.state.twitch_login or "")

        # Atualiza token_store
        from services.token_store import load_token, save_token
        saved = load_token("twitch") or {}
        saved["access_token"]  = new_token
        saved["refresh_token"] = new_refresh
        save_token("twitch", saved)

        logger.info("[TokenRefresh] Twitch access_token renovado")
        return True

    except Exception as e:
        logger.warning(f"[TokenRefresh] Twitch erro: {e}")
        return False


# ── Kick ───────────────────────────────────────────────────────────────────────

_KICK_INVALID_STATUSES = {401, 403}

async def validate_kick(app: "FastAPI") -> tuple[bool, bool]:
    """
    Valida o token Kick chamando a API de usuário.
    Retorna (válido, definitivamente_inválido).
    definitivamente_inválido=True apenas em 401/403 — outros erros são inconclusivos.
    """
    token = getattr(app.state, "kick_user_token", None)
    if not token:
        return False, True
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.kick.com/public/v1/user",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                timeout=10,
            )
            if resp.status_code == 200:
                data    = resp.json().get("data", {})
                channel = data.get("username", "")
                logger.info(f"[TokenRefresh] Kick token válido para '{channel}'")
                return True, False
            definitive = resp.status_code in _KICK_INVALID_STATUSES
            logger.warning(f"[TokenRefresh] Kick validate: {resp.status_code} (definitivo={definitive})")
            return False, definitive
    except Exception as e:
        # Erro de rede/timeout — não apaga o token
        logger.debug(f"[TokenRefresh] Kick validate erro de rede: {e}")
        return False, False


# ── Background loop ────────────────────────────────────────────────────────────

async def start_refresh_loop(app: "FastAPI"):
    """
    Loop único que gerencia todos os refreshes:
    - Valida todos os tokens imediatamente no startup
    - Renova YouTube a cada 50 min
    - Renova Twitch a cada 30 dias (ou se a validação falhar)
    """
    # ── Validação imediata no startup ─────────────────────────────────
    await _startup_validation(app)

    yt_elapsed     = 0
    twitch_elapsed = 0
    tick           = 60  # checa a cada 60s

    while True:
        await asyncio.sleep(tick)
        yt_elapsed     += tick
        twitch_elapsed += tick

        # YouTube: renova a cada 50 min
        if yt_elapsed >= YOUTUBE_REFRESH_INTERVAL:
            yt_elapsed = 0
            if getattr(app.state, "youtube_refresh_token", None):
                await refresh_youtube(app)

        # Twitch: renova a cada 30 dias
        if twitch_elapsed >= TWITCH_REFRESH_INTERVAL:
            twitch_elapsed = 0
            if getattr(app.state, "twitch_refresh_token", None):
                ok = await validate_twitch(app)
                if not ok:
                    await refresh_twitch(app)


async def _startup_validation(app: "FastAPI"):
    """Valida todos os tokens restaurados do disco. Remove os inválidos e tenta refresh."""
    logger.info("[TokenRefresh] Validando tokens restaurados...")

    # Twitch
    if getattr(app.state, "twitch_user_token", None):
        ok = await validate_twitch(app)
        if not ok:
            logger.warning("[TokenRefresh] Twitch token inválido — tentando refresh")
            ok = await refresh_twitch(app)
            if not ok:
                logger.warning("[TokenRefresh] Twitch refresh falhou — requer nova autenticação")
                app.state.twitch_user_token = None
                from services.token_store import clear_token
                clear_token("twitch")

    # YouTube: testa fazendo uma chamada leve
    if getattr(app.state, "youtube_access_token", None):
        ok = await _validate_youtube(app)
        if not ok:
            logger.warning("[TokenRefresh] YouTube token inválido — tentando refresh")
            ok = await refresh_youtube(app)
            if not ok:
                logger.warning("[TokenRefresh] YouTube refresh falhou — requer nova autenticação")
                app.state.youtube_access_token = None
                from services.token_store import clear_token
                clear_token("youtube")

    # Kick — só limpa se o servidor confirmar que o token é inválido (401/403)
    if getattr(app.state, "kick_user_token", None):
        ok, definitive = await validate_kick(app)
        if not ok and definitive:
            logger.warning("[TokenRefresh] Kick token rejeitado pelo servidor — requer nova autenticação")
            app.state.kick_user_token = None
            ki_svc = getattr(app.state, "kick", None)
            if ki_svc:
                ki_svc.set_user_token("")
            from services.token_store import clear_token
            clear_token("kick")
        elif not ok:
            logger.info("[TokenRefresh] Kick validate inconclusivo (API instável) — mantendo token")

    logger.info("[TokenRefresh] Validação de startup concluída")


async def _validate_youtube(app: "FastAPI") -> bool:
    token = getattr(app.state, "youtube_access_token", None)
    if not token:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v1/tokeninfo",
                params={"access_token": token},
                timeout=10,
            )
            return resp.status_code == 200
    except Exception:
        return False


# ── Helper ─────────────────────────────────────────────────────────────────────

def _get_setting(app: "FastAPI", key: str) -> str:
    try:
        from config import get_settings
        return getattr(get_settings(), key, "") or ""
    except Exception:
        return ""
