"""
Token Store — persiste tokens OAuth criptografados em disco.

Arquivos gerados (nunca commitar):
  tokens.key  → chave de criptografia Fernet (gerada 1x automaticamente)
  tokens.enc  → tokens criptografados (AES-128-CBC + HMAC-SHA256)

Fluxo:
  1ª execução  → gera tokens.key, tokens.enc vazio
  OAuth OK     → save_token(platform, data)  → criptografa e persiste
  App restart  → load_all()                  → decripta e retorna tokens
  Token ruim   → clear_token(platform)       → remove plataforma
"""
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_KEY_FILE    = Path("tokens.key")
_TOKENS_FILE = Path("tokens.enc")

_fernet = None  # inicializado em _get_fernet()


def _get_fernet():
    """Retorna instância Fernet, criando a chave se necessário."""
    global _fernet
    if _fernet is not None:
        return _fernet

    try:
        from cryptography.fernet import Fernet
    except ImportError:
        logger.error(
            "[TokenStore] 'cryptography' não instalado.\n"
            "  Execute: pip install cryptography"
        )
        return None

    if _KEY_FILE.exists():
        key = _KEY_FILE.read_bytes()
    else:
        key = Fernet.generate_key()
        _KEY_FILE.write_bytes(key)
        # Permissões restritas (owner read-only) — só funciona em Unix;
        # no Windows o NTFS já restringe ao perfil do usuário logado.
        try:
            import stat
            _KEY_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
        logger.info("[TokenStore] Chave de criptografia gerada em tokens.key")

    from cryptography.fernet import Fernet
    _fernet = Fernet(key)
    return _fernet


def _load_raw() -> dict:
    """Lê e decripta o arquivo de tokens. Retorna {} se não existir ou falhar."""
    f = _get_fernet()
    if f is None or not _TOKENS_FILE.exists():
        return {}
    try:
        encrypted = _TOKENS_FILE.read_bytes()
        plain     = f.decrypt(encrypted)
        return json.loads(plain)
    except Exception as e:
        logger.warning(f"[TokenStore] Falha ao ler tokens.enc: {e}")
        return {}


def _save_raw(data: dict) -> None:
    """Criptografa e salva o dicionário de tokens."""
    f = _get_fernet()
    if f is None:
        return
    try:
        plain     = json.dumps(data, ensure_ascii=False).encode()
        encrypted = f.encrypt(plain)
        _TOKENS_FILE.write_bytes(encrypted)
    except Exception as e:
        logger.warning(f"[TokenStore] Falha ao salvar tokens.enc: {e}")


# ── API pública ──────────────────────────────────────────────────────────────

def save_token(platform: str, data: dict) -> None:
    """
    Salva (ou atualiza) tokens de uma plataforma.
    data pode conter: access_token, refresh_token, channel_id, channel_name, login, etc.
    """
    tokens = _load_raw()
    tokens[platform] = data
    _save_raw(tokens)
    logger.info(f"[TokenStore] Token '{platform}' salvo")


def load_token(platform: str) -> Optional[dict]:
    """Retorna o dict de tokens de uma plataforma, ou None se não existir."""
    return _load_raw().get(platform)


def load_all() -> dict:
    """Retorna todos os tokens salvos."""
    return _load_raw()


def clear_token(platform: str) -> None:
    """Remove o token de uma plataforma (ex: após logout ou token inválido)."""
    tokens = _load_raw()
    if platform in tokens:
        del tokens[platform]
        _save_raw(tokens)
        logger.info(f"[TokenStore] Token '{platform}' removido")


def clear_all() -> None:
    """Remove todos os tokens (reset completo)."""
    _save_raw({})
    logger.info("[TokenStore] Todos os tokens removidos")
