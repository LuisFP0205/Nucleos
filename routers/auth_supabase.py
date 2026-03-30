"""
Supabase auth helpers.

GET  /auth/supabase/config    → expõe SUPABASE_URL e SUPABASE_ANON_KEY ao frontend
GET  /auth/supabase/callback  → serve a página de callback OAuth
GET  /login                   → serve a página de login
"""
import sys
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from config import get_settings
from routers.chat import set_history_limit

_ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))

# Estado em memória — atualizado pelo frontend após login
_is_premium: bool = False
_current_user: dict = {}

router = APIRouter(tags=["auth-supabase"])


@router.get("/auth/supabase/config", include_in_schema=False)
async def supabase_config():
    """
    Retorna as chaves públicas do Supabase para uso no frontend.
    O anon_key é seguro para expor — é projetado para uso no browser.
    Se SUPABASE_URL não estiver configurado, retorna enabled=False.
    """
    s = get_settings()
    if not s.supabase_url or not s.supabase_anon_key:
        return JSONResponse({"enabled": False, "url": "", "anon_key": ""})
    return JSONResponse({
        "enabled": True,
        "url": s.supabase_url,
        "anon_key": s.supabase_anon_key,
    })


@router.get("/auth/supabase/callback", include_in_schema=False)
async def supabase_callback():
    return FileResponse(str(_ASSETS / "static" / "auth-callback.html"))


@router.get("/auth/reset-password", include_in_schema=False)
async def reset_password_page():
    return FileResponse(str(_ASSETS / "static" / "reset-password.html"))


@router.get("/auth/plan", include_in_schema=False)
async def get_plan():
    """Retorna o plano atual do usuário logado (lido pelos overlays)."""
    return JSONResponse({"is_premium": _is_premium})


@router.post("/auth/plan", include_in_schema=False)
async def set_plan(request: Request):
    """Frontend chama este endpoint após login para sincronizar plano e usuário ao servidor."""
    global _is_premium, _current_user
    data = await request.json()
    _is_premium = bool(data.get("is_premium", False))
    if data.get("email"):
        _current_user = {"email": data["email"], "display_name": data.get("display_name", "")}
    set_history_limit(_is_premium)
    return JSONResponse({"ok": True})


@router.get("/login", include_in_schema=False)
async def login_page():
    return FileResponse(str(_ASSETS / "static" / "login.html"))
