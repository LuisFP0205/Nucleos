"""
Kick service: live stream detection (public API) + live chat via Pusher WebSocket.

Detecção via API pública do Kick (sem autenticação):
  GET https://kick.com/api/v2/channels/{slug}
  → retorna livestream (null se offline), chatroom.id, viewer_count

A API usa Cloudflare. Utilizamos curl_cffi para imitar a fingerprint TLS do
Chrome e passar pela proteção sem necessidade de cookies ou tokens.

Chat via Pusher WebSocket:
  wss://ws-us2.pusher.com/app/eb1d5f283081a78b932c
  Canal:  chatrooms.{chatroom_id}.v2
  Evento: App\\Events\\ChatMessageEvent
"""
import asyncio
import html as _html
import json
import logging
import re
from typing import Callable, Optional

# Suporta websockets 10–14: tenta a nova API asyncio (>=13), cai para a legacy
try:
    from websockets.asyncio.client import connect as _ws_connect
except ImportError:
    from websockets.legacy.client import connect as _ws_connect  # type: ignore

logger = logging.getLogger(__name__)

KICK_API_BASE  = "https://kick.com/api/v2"
PUSHER_APP_KEY = "32cbd69e4b950bf97679"
PUSHER_URL     = (
    f"wss://ws-us2.pusher.com/app/{PUSHER_APP_KEY}"
    "?protocol=7&client=js&version=8.4.0-rc2&flash=false"
)

_HEADERS = {
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://kick.com/",
    "Origin":          "https://kick.com",
}


_KICK_EMOTE_CDN = "https://files.kick.com/emotes/{id}/fullsize"
_EMOTE_RE       = re.compile(r'\[emote:(\d+):([^\]]+)\]')


def _build_kick_html(content: str) -> str:
    """Substitui marcadores [emote:id:name] por <img> tags do CDN do Kick."""
    parts: list[str] = []
    prev = 0
    for m in _EMOTE_RE.finditer(content):
        if m.start() > prev:
            parts.append(_html.escape(content[prev:m.start()]))
        emote_id   = m.group(1)
        emote_name = _html.escape(m.group(2))
        url        = _KICK_EMOTE_CDN.format(id=emote_id)
        parts.append(
            f'<img class="chat-emote" src="{url}" alt="{emote_name}" title="{emote_name}">'
        )
        prev = m.end()
    if prev < len(content):
        parts.append(_html.escape(content[prev:]))
    return "".join(parts) if parts else _html.escape(content)


def _make_client():
    """Cria um AsyncSession curl_cffi que imita o Chrome (bypassa Cloudflare)."""
    try:
        from curl_cffi.requests import AsyncSession
        return AsyncSession(impersonate="chrome", headers=_HEADERS)
    except ImportError:
        logger.error(
            "[Kick] curl_cffi não instalado. Execute: pip install curl-cffi\n"
            "       Sem ele, a API do Kick é bloqueada pelo Cloudflare."
        )
        return None


KICK_PUBLIC_API = "https://api.kick.com/public/v1"


class KickService:
    def __init__(self, channel: str):
        self.channel      = channel.lower().strip()
        self._chatroom_id: Optional[int]  = None
        self._chat_task:   Optional[asyncio.Task] = None
        self._on_message:  Optional[Callable]     = None
        self._connected    = False
        self._user_token:  Optional[str]  = None   # OAuth token para envio

    def set_user_token(self, token: str) -> None:
        """Armazena o OAuth token do Kick (necessário para enviar mensagens)."""
        self._user_token = token or None

    # ------------------------------------------------------------------ #
    # Stream Detection                                                     #
    # ------------------------------------------------------------------ #

    async def get_stream_info(self) -> Optional[dict]:
        """
        Retorna dict com info da live se o canal estiver ao vivo, senão None.
        Chaves: id, title, viewer_count, chatroom_id
        """
        if not self.channel:
            return None

        client = _make_client()
        if client is None:
            return None

        try:
            async with client:
                resp = await client.get(
                    f"{KICK_API_BASE}/channels/{self.channel}",
                    timeout=15,
                )

                if resp.status_code == 404:
                    logger.warning(f"[Kick] Canal '{self.channel}' não encontrado (404)")
                    return None

                if resp.status_code == 403:
                    logger.error(
                        f"[Kick] Acesso negado (403) mesmo com curl_cffi.\n"
                        f"  Resposta: {resp.text[:300]}"
                    )
                    return None

                if resp.status_code != 200:
                    logger.error(
                        f"[Kick] Status inesperado {resp.status_code}: {resp.text[:300]}"
                    )
                    return None

                # Tenta fazer parse do JSON; se falhar, provavelmente é HTML do Cloudflare
                try:
                    data = resp.json()
                except Exception:
                    logger.error(
                        f"[Kick] Resposta não é JSON (provável bloqueio Cloudflare).\n"
                        f"  Primeiros 300 chars: {resp.text[:300]}"
                    )
                    return None

            self._chatroom_id = data.get("chatroom", {}).get("id")
            livestream = data.get("livestream")
            if not livestream:
                return None

            return {
                "id":           str(livestream.get("id", "")),
                "title":        livestream.get("session_title", ""),
                "viewer_count": int(livestream.get("viewer_count", 0)),
                "chatroom_id":  self._chatroom_id,
                "started_at":   livestream.get("created_at"),
            }

        except Exception as e:
            logger.error(f"[Kick] Erro na detecção: {type(e).__name__}: {e}")
        return None

    # ------------------------------------------------------------------ #
    # Pusher Chat                                                          #
    # ------------------------------------------------------------------ #

    async def _pusher_loop(self, chatroom_id: int):
        """Conecta ao Pusher WebSocket do Kick e retransmite mensagens do chat."""
        channel = f"chatrooms.{chatroom_id}.v2"

        while True:
            try:
                async with _ws_connect(PUSHER_URL) as ws:
                    logger.info(f"[Kick Chat] Conectado ao Pusher — canal '{channel}'")

                    # Subscreve ao chatroom
                    await ws.send(json.dumps({
                        "event": "pusher:subscribe",
                        "data":  {"auth": "", "channel": channel},
                    }))

                    self._connected = True

                    async for raw in ws:
                        msg   = json.loads(raw)
                        event = msg.get("event", "")

                        if event == "pusher:ping":
                            await ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                            continue

                        if event == "pusher_internal:subscription_succeeded":
                            logger.info(f"[Kick Chat] Subscrito com sucesso em '{channel}'")
                            continue

                        # O evento chega com barra simples após json.loads
                        if event not in ("App\\Events\\ChatMessageEvent",
                                         r"App\Events\ChatMessageEvent"):
                            continue

                        raw_data = msg.get("data", "{}")
                        payload  = json.loads(raw_data) if isinstance(raw_data, str) else raw_data

                        # Filtra apenas mensagens de texto (ignora gifted subs, etc.)
                        if payload.get("type", "message") != "message":
                            continue

                        content  = payload.get("content", "").strip()
                        sender   = payload.get("sender", {})
                        username = sender.get("username", "")
                        identity = sender.get("identity", {})
                        color    = identity.get("color") or "#53FC18"

                        badges = [
                            b.get("type", "")
                            for b in identity.get("badges", [])
                            if b.get("type")
                        ]

                        if self._on_message and content:
                            await self._on_message({
                                "platform":     "kick",
                                "user":         username,
                                "message":      content,
                                "message_html": _build_kick_html(content),
                                "color":        color,
                                "badges":       badges,
                            })

            except asyncio.CancelledError:
                logger.info("[Kick Chat] Task cancelada")
                break
            except Exception as e:
                logger.warning(f"[Kick Chat] Reconectando em 10s — {type(e).__name__}: {e}")
                self._connected = False
                await asyncio.sleep(10)

        self._connected = False

    async def send_message(self, text: str) -> bool:
        """Envia mensagem no chat via Kick Public API v1 (requer OAuth token)."""
        if not self._user_token:
            logger.debug("[Kick] send_message ignorado: sem OAuth token")
            return False
        if not self._chatroom_id:
            logger.debug("[Kick] send_message ignorado: chatroom_id desconhecido")
            return False
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{KICK_PUBLIC_API}/chat",
                    headers={
                        "Authorization": f"Bearer {self._user_token}",
                        "Content-Type":  "application/json",
                        "Accept":        "application/json",
                    },
                    json={"chatroom_id": self._chatroom_id, "content": text, "type": "message"},
                    timeout=10,
                )
                if resp.status_code in (200, 201):
                    return True
                logger.warning(f"[Kick] Falha ao enviar mensagem: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"[Kick] Erro ao enviar mensagem: {e}")
        return False

    def start_chat(self, chatroom_id: int, on_message: Callable):
        if self._chat_task and not self._chat_task.done():
            return
        self._on_message = on_message
        self._chat_task  = asyncio.create_task(self._pusher_loop(chatroom_id))
        logger.info(f"[Kick] Chat listener iniciado (chatroom_id={chatroom_id})")

    def stop_chat(self):
        if self._chat_task:
            self._chat_task.cancel()
            self._chat_task = None
        self._connected = False

    @property
    def chat_connected(self) -> bool:
        return self._connected
