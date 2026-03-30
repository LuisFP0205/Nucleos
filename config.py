import sys
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


def _find_env_file() -> Path:
    """
    Localiza o .env independente do cwd.
    - Dev: pasta do projeto (cwd normal)
    - Exe empacotado: pasta do executável (um nível acima de _internal/)
    """
    if getattr(sys, "frozen", False):
        # Executável PyInstaller: .env fica ao lado do Nucleus.exe
        return Path(sys.executable).parent / ".env"
    return Path(".env")


_ENV_FILE = _find_env_file()


class Settings(BaseSettings):
    # Twitch (client_secret fica no Supabase Edge Function)
    twitch_client_id: str = ""
    twitch_channel: str = ""

    # YouTube (api_key e google_client_secret ficam no Supabase Edge Function)
    youtube_channel_id: str = ""
    google_client_id: str = ""

    # Kick (kick_client_secret fica no Supabase Edge Function)
    kick_channel: str = ""
    kick_client_id: str = ""

    # Server
    port: int = 3000
    host: str = "0.0.0.0"

    # Stream detection interval (seconds)
    stream_check_interval: int = 30

    # OBS WebSocket (opcional — requer OBS 28+ com WebSocket Server ativado)
    obs_host: str = "localhost"
    obs_port: int = 4455
    obs_password: str = ""

    # Supabase (opcional — deixe em branco para desativar login)
    supabase_url: str = ""
    supabase_anon_key: str = ""

    class Config:
        env_file = str(_ENV_FILE)
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
