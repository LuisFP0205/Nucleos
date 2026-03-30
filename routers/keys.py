"""
Gerenciamento de API Keys via interface web.
GET  /keys        → retorna as chaves atuais (secrets parcialmente mascarados)
POST /keys        → salva no .env e reinicia o cache de settings
"""
import logging
import os
import sys
import threading
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/keys", tags=["keys"])

ENV_FILE = Path(".env")

# Campos gerenciados por esta rota (secrets ficam no Supabase Edge Functions)
_FIELDS = [
    "TWITCH_CLIENT_ID",
    "GOOGLE_CLIENT_ID",
    "KICK_CLIENT_ID",
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
]


class ApiKeys(BaseModel):
    twitch_client_id:  str = ""
    google_client_id:  str = ""
    kick_client_id:    str = ""
    supabase_url:      str = ""
    supabase_anon_key: str = ""


def _read_env() -> dict[str, str]:
    """Lê o .env e retorna um dicionário com as chaves."""
    values: dict[str, str] = {f: "" for f in _FIELDS}
    if not ENV_FILE.exists():
        return values
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip().upper()
            if key in values:
                values[key] = val.strip()
    return values


def _write_env(new_values: dict[str, str]):
    """Atualiza as chaves no .env, preservando comentários e outras variáveis."""
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    updated = set()
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip().upper()
            if key in new_values:
                result.append(f"{key}={new_values[key]}")
                updated.add(key)
                continue
        result.append(line)

    # Adiciona chaves que ainda não existiam no arquivo
    for key in _FIELDS:
        if key not in updated:
            result.append(f"{key}={new_values.get(key, '')}")

    ENV_FILE.write_text("\n".join(result) + "\n", encoding="utf-8")


def _mask(value: str) -> str:
    """Mascara parcialmente um valor sensível: ab...xyz"""
    if len(value) <= 6:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 6) + value[-3:]


@router.get("")
async def get_keys():
    """Retorna as chaves atuais."""
    env = _read_env()
    return {
        "twitch_client_id":  env["TWITCH_CLIENT_ID"],
        "google_client_id":  env["GOOGLE_CLIENT_ID"],
        "kick_client_id":    env["KICK_CLIENT_ID"],
        "supabase_url":      env["SUPABASE_URL"],
        "supabase_anon_key": _mask(env["SUPABASE_ANON_KEY"]) if env["SUPABASE_ANON_KEY"] else "",
        "supabase_anon_key_set": bool(env["SUPABASE_ANON_KEY"]),
    }


@router.post("")
async def save_keys(body: ApiKeys):
    """
    Salva as chaves no .env.
    Campos em branco que já tinham valor são ignorados (preserva o valor atual).
    """
    env = _read_env()

    def apply(env_key: str, new_val: str):
        if new_val.strip():
            env[env_key] = new_val.strip()

    apply("TWITCH_CLIENT_ID",  body.twitch_client_id)
    apply("GOOGLE_CLIENT_ID",  body.google_client_id)
    apply("KICK_CLIENT_ID",    body.kick_client_id)
    apply("SUPABASE_URL",      body.supabase_url)
    apply("SUPABASE_ANON_KEY", body.supabase_anon_key)

    _write_env(env)

    # Invalida o cache de settings para que próxima leitura pegue os novos valores
    try:
        from config import get_settings
        get_settings.cache_clear()
    except Exception:
        pass

    logger.info("[Keys] Credenciais atualizadas no .env")
    return {"ok": True, "message": "Credenciais salvas. Reinicie o servidor para aplicar as novas keys."}


@router.post("/restart")
async def restart_server():
    """Reinicia o processo do servidor."""
    def _do_restart():
        import subprocess
        logger.info("[Keys] Reiniciando servidor...")
        args = [a for a in sys.argv[1:] if a not in ("--no-browser",) and not a.startswith("--restart-url=")]
        subprocess.Popen([sys.executable] + args + ["--no-browser", "--restart-url=/keys-config", "--wait-port-free"])
        os._exit(0)

    threading.Timer(2.0, _do_restart).start()
    return {"ok": True, "message": "Reiniciando..."}
