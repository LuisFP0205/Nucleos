"""
Autenticação OAuth 2.0 — Twitch, YouTube (Google) e Kick.

Redirect URIs a cadastrar:
  Twitch:  http://localhost:3000/auth/twitch/callback
  YouTube: http://localhost:3000/auth/youtube/callback
  Kick:    http://localhost:3000/auth/kick/callback
"""
import base64
import hashlib
import secrets
import logging
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, HTMLResponse

from config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

TWITCH_AUTHORIZE_URL = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN_URL     = "https://id.twitch.tv/oauth2/token"
TWITCH_VALIDATE_URL  = "https://id.twitch.tv/oauth2/validate"

# Scopes necessários: leitura + envio de mensagens + criar clips
SCOPES = "chat:read chat:edit clips:edit"

# State gerado por requisição para proteger contra CSRF
# (app local/single-user, então uma variável em memória é suficiente)
_pending_state: str = ""


@router.get("/twitch")
async def twitch_login(request: Request):
    """Inicia o fluxo OAuth redirecionando o usuário para a Twitch."""
    global _pending_state
    settings = get_settings()

    if not settings.twitch_client_id:
        return HTMLResponse(
            "<h3>Configure TWITCH_CLIENT_ID no arquivo .env antes de autenticar.</h3>",
            status_code=400,
        )

    _pending_state = secrets.token_urlsafe(16)
    redirect_uri = _build_redirect_uri(request)

    params = (
        f"client_id={settings.twitch_client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={SCOPES.replace(' ', '+')}"
        f"&state={_pending_state}"
        f"&force_verify=true"
    )
    return RedirectResponse(f"{TWITCH_AUTHORIZE_URL}?{params}")


@router.get("/twitch/callback")
async def twitch_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """
    Recebe o retorno da Twitch após a autorização.
    Troca o authorization code por um User Access Token e o armazena no app.state.
    """
    global _pending_state
    settings = get_settings()

    if error:
        logger.warning(f"[Auth] Twitch retornou erro: {error}")
        return _html_result(False, f"Twitch recusou a autorização: {error}")

    if state != _pending_state:
        logger.warning("[Auth] State inválido – possível CSRF")
        return _html_result(False, "State inválido. Tente novamente.")

    _pending_state = ""
    redirect_uri = _build_redirect_uri(request)

    try:
        fn_url = f"{settings.supabase_url}/functions/v1/twitch-token"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                fn_url,
                json={"code": code, "redirect_uri": redirect_uri},
                headers={"Authorization": f"Bearer {settings.supabase_anon_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

        access_token  = data["access_token"]
        refresh_token = data.get("refresh_token", "")

        # Valida o token e obtém o login do usuário
        async with httpx.AsyncClient() as client:
            val = await client.get(
                TWITCH_VALIDATE_URL,
                headers={"Authorization": f"OAuth {access_token}"},
            )
            val.raise_for_status()
            val_data = val.json()

        login = val_data.get("login", "desconhecido")
        logger.info(f"[Auth] Twitch autenticado como: {login}")

        # Armazena no app.state e atualiza o TwitchService
        app = request.app
        app.state.twitch_user_token   = access_token
        app.state.twitch_refresh_token = refresh_token
        app.state.twitch_login        = login

        twitch_svc = getattr(app.state, "twitch", None)
        if twitch_svc:
            twitch_svc.set_user_token(access_token, login)

        # Persiste tokens criptografados para reconexão automática
        try:
            from services.token_store import save_token
            save_token("twitch", {
                "access_token":  access_token,
                "refresh_token": refresh_token,
                "login":         login,
            })
        except Exception as e:
            logger.warning(f"[Auth] Falha ao persistir token Twitch: {e}")

        return _html_result(True, f"Autenticado como <strong>{login}</strong>.")

    except Exception as e:
        logger.error(f"[Auth] Falha ao trocar token: {e}")
        return _html_result(False, f"Erro ao obter token: {e}")


@router.get("/status")
async def all_auth_status(request: Request):
    """Retorna status de conexão das 3 plataformas de uma vez."""
    app = request.app
    tw  = getattr(app.state, "twitch_user_token",   None)
    yt  = getattr(app.state, "youtube_access_token", None)
    ki  = getattr(app.state, "kick_user_token",      None)

    twitch_svc  = getattr(app.state, "twitch",  None)
    youtube_svc = getattr(app.state, "youtube", None)
    kick_svc    = getattr(app.state, "kick",    None)

    return {
        "twitch":  {
            "authenticated": bool(tw),
            "login":         getattr(app.state, "twitch_login", "") or "",
            "channel":       twitch_svc.channel  if twitch_svc  else "",
        },
        "youtube": {
            "authenticated": bool(yt),
            "channel_id":    youtube_svc.channel_id if youtube_svc else "",
        },
        "kick": {
            "authenticated": bool(ki),
            "channel":       kick_svc.channel    if kick_svc    else "",
        },
    }


@router.get("/twitch/status")
async def twitch_auth_status(request: Request):
    """Retorna se o token de usuário Twitch está presente e qual login está autenticado."""
    app = request.app
    token = getattr(app.state, "twitch_user_token", None)
    login = getattr(app.state, "twitch_login", None)
    return {
        "authenticated": bool(token),
        "login": login,
    }


@router.delete("/twitch")
async def twitch_logout(request: Request):
    """Remove o token de usuário da memória (logout local)."""
    app = request.app
    app.state.twitch_user_token    = None
    app.state.twitch_refresh_token = None
    app.state.twitch_login         = None

    twitch_svc = getattr(app.state, "twitch", None)
    if twitch_svc:
        twitch_svc.set_user_token("", "")

    try:
        from services.token_store import clear_token
        clear_token("twitch")
    except Exception:
        pass

    return {"ok": True}


# ── Kick OAuth ───────────────────────────────────────────────────────────────

KICK_AUTHORIZE_URL = "https://id.kick.com/oauth/authorize"
KICK_TOKEN_URL     = "https://id.kick.com/oauth/token"
KICK_SCOPES        = "chat:read chat:write"

_kick_pending_state:   str = ""
_kick_code_verifier:   str = ""


def _pkce_pair() -> tuple[str, str]:
    """Gera (code_verifier, code_challenge) para PKCE S256."""
    verifier  = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


@router.get("/kick")
async def kick_login(request: Request):
    """Inicia o fluxo OAuth do Kick (com PKCE S256)."""
    global _kick_pending_state, _kick_code_verifier
    settings = get_settings()

    if not getattr(settings, "kick_client_id", None):
        return HTMLResponse(
            "<h3>Configure KICK_CLIENT_ID no arquivo .env antes de autenticar.</h3>",
            status_code=400,
        )

    _kick_pending_state          = secrets.token_urlsafe(16)
    _kick_code_verifier, challenge = _pkce_pair()
    redirect_uri                 = _build_kick_redirect_uri(request)

    import urllib.parse
    params = urllib.parse.urlencode({
        "client_id":             settings.kick_client_id,
        "redirect_uri":          redirect_uri,
        "response_type":         "code",
        "scope":                 KICK_SCOPES,
        "state":                 _kick_pending_state,
        "code_challenge":        challenge,
        "code_challenge_method": "S256",
    })
    return RedirectResponse(f"{KICK_AUTHORIZE_URL}?{params}")


@router.get("/kick/callback")
async def kick_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """Recebe o callback do Kick após autorização."""
    global _kick_pending_state, _kick_code_verifier
    settings = get_settings()

    if error:
        return _html_result(False, f"Kick recusou a autorização: {error}", "kick")

    if state != _kick_pending_state:
        return _html_result(False, "State inválido. Tente novamente.", "kick")

    _kick_pending_state = ""
    redirect_uri        = _build_kick_redirect_uri(request)
    verifier            = _kick_code_verifier
    _kick_code_verifier = ""

    try:
        fn_url = f"{settings.supabase_url}/functions/v1/kick-token"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                fn_url,
                json={"code": code, "redirect_uri": redirect_uri, "code_verifier": verifier},
                headers={"Authorization": f"Bearer {settings.supabase_anon_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

        access_token = data.get("access_token", "")
        if not access_token:
            return _html_result(False, f"Token não retornado pelo Kick: {data}", "kick")

        # Busca username do usuário autenticado
        username = ""
        try:
            async with httpx.AsyncClient() as client:
                u_resp = await client.get(
                    "https://api.kick.com/public/v1/user",
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                    timeout=10,
                )
                if u_resp.status_code == 200:
                    username = u_resp.json().get("data", {}).get("username", "")
                    logger.info(f"[Auth Kick] Autenticado como '{username}'")
                else:
                    logger.warning(f"[Auth Kick] Não foi possível buscar username: {u_resp.status_code}")
        except Exception as e:
            logger.warning(f"[Auth Kick] Erro ao buscar username: {e}")

        app = request.app
        app.state.kick_user_token = access_token

        kick_svc = getattr(app.state, "kick", None)
        if kick_svc:
            kick_svc.set_user_token(access_token)
            if username:
                kick_svc.channel = username.lower()

        # Salva canal no runtime_settings para detecção de live
        if username:
            try:
                from routers.settings import load_runtime_settings, save_runtime_settings
                rt = load_runtime_settings()
                rt.kick_channel = username.lower()
                save_runtime_settings(rt)
            except Exception as e:
                logger.warning(f"[Auth Kick] Falha ao salvar kick_channel: {e}")

        # Persiste token criptografado
        try:
            from services.token_store import save_token
            save_token("kick", {"access_token": access_token, "username": username})
        except Exception as e:
            logger.warning(f"[Auth] Falha ao persistir token Kick: {e}")

        name_str = f" — canal: <strong>{username}</strong>" if username else ""
        return _html_result(True, f"Kick autenticado com sucesso{name_str}! Envio de mensagens ativado.", "kick")

    except Exception as e:
        logger.error(f"[Auth Kick] Falha ao trocar token: {e}")
        return _html_result(False, f"Erro ao obter token: {e}", "kick")


@router.get("/kick/token-info")
async def kick_token_info():
    """Retorna metadados não-sensíveis do token Kick salvo (username)."""
    try:
        from services.token_store import load_token
        tk = load_token("kick") or {}
        return {"username": tk.get("username", "")}
    except Exception:
        return {"username": ""}


@router.get("/kick/status")
async def kick_auth_status(request: Request):
    app   = request.app
    token = getattr(app.state, "kick_user_token", None)
    return {"authenticated": bool(token)}


@router.delete("/kick")
async def kick_logout(request: Request):
    app = request.app
    app.state.kick_user_token = None
    kick_svc = getattr(app.state, "kick", None)
    if kick_svc:
        kick_svc.set_user_token("")

    try:
        from services.token_store import clear_token
        clear_token("kick")
    except Exception:
        pass

    return {"ok": True}


# ── YouTube / Google OAuth ────────────────────────────────────────────────────

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL     = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL  = "https://www.googleapis.com/youtube/v3/channels"

# youtube.readonly  → leitura de canal/stream
# youtube.force-ssl → enviar mensagens no chat
GOOGLE_SCOPES = " ".join([
    "openid",
    "https://www.googleapis.com/auth/youtube",  # inclui readonly + force-ssl em um só escopo
])

_yt_pending_state: str = ""


@router.get("/youtube")
async def youtube_login(request: Request):
    """Inicia o fluxo OAuth do YouTube (Google)."""
    global _yt_pending_state
    settings = get_settings()

    if not settings.google_client_id:
        return HTMLResponse(
            "<h3>Configure GOOGLE_CLIENT_ID no arquivo .env antes de autenticar.</h3>",
            status_code=400,
        )

    _yt_pending_state = secrets.token_urlsafe(16)
    redirect_uri      = _build_yt_redirect_uri(request)

    import urllib.parse
    params = urllib.parse.urlencode({
        "client_id":             settings.google_client_id,
        "redirect_uri":          redirect_uri,
        "response_type":         "code",
        "scope":                 GOOGLE_SCOPES,
        "state":                 _yt_pending_state,
        "access_type":           "offline",
        "prompt":                "consent",
        "include_granted_scopes": "true",  # pré-seleciona todos os escopos solicitados
    })
    return RedirectResponse(f"{GOOGLE_AUTHORIZE_URL}?{params}")


@router.get("/youtube/callback")
async def youtube_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    """Recebe o callback do Google após autorização."""
    global _yt_pending_state
    settings = get_settings()

    if error:
        return _html_result(False, f"Google recusou a autorização: {error}")

    if state != _yt_pending_state:
        return _html_result(False, "State inválido. Tente novamente.")

    _yt_pending_state = ""
    redirect_uri      = _build_yt_redirect_uri(request)

    try:
        # 1 — Troca code por tokens via Supabase Edge Function
        fn_url = f"{settings.supabase_url}/functions/v1/google-token"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                fn_url,
                json={"code": code, "redirect_uri": redirect_uri},
                headers={"Authorization": f"Bearer {settings.supabase_anon_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            token_data = resp.json()

        access_token  = token_data.get("access_token", "")
        refresh_token = token_data.get("refresh_token", "")

        if not access_token:
            return _html_result(False, f"Token não retornado pelo Google: {token_data}")

        # 2 — Busca dados do canal YouTube do usuário autenticado
        channel_id   = ""
        channel_name = ""
        try:
            async with httpx.AsyncClient() as client:
                ch_resp = await client.get(
                    GOOGLE_USERINFO_URL,
                    params={"part": "snippet", "mine": "true"},
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=10,
                )
                ch_data = ch_resp.json()
                items   = ch_data.get("items", [])
                if items:
                    channel_id   = items[0]["id"]
                    channel_name = items[0]["snippet"]["title"]
        except Exception as e:
            logger.warning(f"[Auth YouTube] Falha ao buscar canal: {e}")

        # 3 — Aplica nos serviços em execução
        app = request.app
        app.state.youtube_access_token  = access_token
        app.state.youtube_refresh_token = refresh_token

        youtube_svc = getattr(app.state, "youtube", None)
        if youtube_svc:
            youtube_svc.set_oauth_token(access_token)
            if channel_id:
                youtube_svc.channel_id   = channel_id
                youtube_svc._api_blocked = False

        # 4 — Salva canal no runtime_settings para a detecção de live
        if channel_id:
            try:
                from routers.settings import load_runtime_settings, save_runtime_settings
                rt = load_runtime_settings()
                rt.youtube_channel_id = channel_id
                save_runtime_settings(rt)
            except Exception as e:
                logger.warning(f"[Auth YouTube] Falha ao salvar channel_id: {e}")

        # 5 — Persiste tokens criptografados
        try:
            from services.token_store import save_token
            save_token("youtube", {
                "access_token":  access_token,
                "refresh_token": refresh_token,
                "channel_id":    channel_id,
                "channel_name":  channel_name,
            })
        except Exception as e:
            logger.warning(f"[Auth YouTube] Falha ao persistir token: {e}")

        name_str = f" — canal: <strong>{channel_name}</strong>" if channel_name else ""
        return _html_result(True, f"YouTube autenticado com sucesso{name_str}.", "youtube")

    except Exception as e:
        logger.error(f"[Auth YouTube] Falha ao trocar token: {e}")
        return _html_result(False, f"Erro ao obter token: {e}", "youtube")


@router.get("/youtube/token-info")
async def youtube_token_info():
    """Retorna metadados não-sensíveis do token YouTube salvo (channel_name, channel_id)."""
    try:
        from services.token_store import load_token
        tk = load_token("youtube") or {}
        return {
            "channel_id":   tk.get("channel_id", ""),
            "channel_name": tk.get("channel_name", ""),
        }
    except Exception:
        return {"channel_id": "", "channel_name": ""}


@router.get("/youtube/status")
async def youtube_auth_status(request: Request):
    app   = request.app
    token = getattr(app.state, "youtube_access_token", None)
    yt    = getattr(app.state, "youtube", None)
    return {
        "authenticated": bool(token),
        "channel_id":   yt.channel_id if yt else "",
    }


@router.delete("/youtube")
async def youtube_logout(request: Request):
    app = request.app
    app.state.youtube_access_token  = None
    app.state.youtube_refresh_token = None

    yt = getattr(app.state, "youtube", None)
    if yt:
        yt.set_oauth_token("")

    try:
        from services.token_store import clear_token
        clear_token("youtube")
    except Exception:
        pass

    return {"ok": True}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _build_redirect_uri(request: Request) -> str:
    return f"{request.base_url}auth/twitch/callback".rstrip("/")


def _build_kick_redirect_uri(request: Request) -> str:
    return f"{request.base_url}auth/kick/callback".rstrip("/")


def _build_yt_redirect_uri(request: Request) -> str:
    return f"{request.base_url}auth/youtube/callback".rstrip("/")


def _html_result(success: bool, message: str, platform: str = "twitch") -> HTMLResponse:
    """Página de resultado OAuth — fecha o popup e notifica o dashboard."""
    icon  = "✅" if success else "❌"
    color = "#1db954" if success else "#e74c3c"
    ok_js = "true" if success else "false"
    close_color = "#1db954" if success else "#e74c3c"
    return HTMLResponse(f"""
<!DOCTYPE html><html><head><meta charset="UTF-8">
<title>Autenticação</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; background: #0e0e10; color: #efeff1;
         display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
  .box {{ text-align: center; padding: 32px; background: #18181b; border-radius: 12px;
          border: 1px solid #2a2a2f; max-width: 360px; }}
  h2   {{ color: {color}; margin-bottom: 12px; font-size: 18px; }}
  p    {{ color: #adadb8; font-size: 14px; line-height: 1.5; margin: 0; }}
  .cnt {{ color: #4b5478; font-size: 12px; margin-top: 20px; }}
</style>
</head><body>
<div class="box">
  <h2>{icon} {('Sucesso' if success else 'Erro')}</h2>
  <p>{message}</p>
  <p class="cnt" id="cnt">Fechando em 3...</p>
</div>
<script>
  try {{
    const bc = new BroadcastChannel('nucleus_oauth');
    bc.postMessage({{ platform: '{platform}', success: {ok_js} }});
    bc.close();
  }} catch(e) {{}}
  let n = 3;
  const el = document.getElementById('cnt');
  const iv = setInterval(() => {{
    n--;
    if (n <= 0) {{
      clearInterval(iv);
      el.textContent = 'Fechando...';
      try {{ window.close(); }} catch(e) {{}}
    }} else {{
      el.textContent = 'Fechando em ' + n + '...';
    }}
  }}, 1000);
</script>
</body></html>
""")
