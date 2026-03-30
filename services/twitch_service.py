"""
Twitch service: live stream detection + IRC chat listener.
"""
import asyncio
import html as _html
import logging
import websockets
from typing import Callable, Optional
import httpx

logger = logging.getLogger(__name__)

TWITCH_IRC_URL  = "wss://irc-ws.chat.twitch.tv:443"
_TWITCH_CDN     = "https://static-cdn.jtvnw.net/emoticons/v2/{id}/default/dark/1.0"


def _build_twitch_html(message: str, emotes_tag: str) -> str:
    """
    Substitui trechos de texto por <img> de emote usando as posições do
    tag @emotes= do IRC da Twitch.
    Formato: emote_id:start-end,start-end/emote_id2:start-end
    """
    if not emotes_tag:
        return _html.escape(message)

    replacements: list[tuple[int, int, str]] = []
    for entry in emotes_tag.split("/"):
        if ":" not in entry:
            continue
        emote_id, positions = entry.split(":", 1)
        # Aceita IDs numéricos ou no formato emotesv2_xxx
        if not emote_id.replace("emotesv2_", "").replace("_", "").isalnum():
            continue
        for pos in positions.split(","):
            if "-" not in pos:
                continue
            try:
                start, end = (int(x) for x in pos.split("-", 1))
                replacements.append((start, end, emote_id))
            except ValueError:
                pass

    if not replacements:
        return _html.escape(message)

    replacements.sort(key=lambda x: x[0])
    parts: list[str] = []
    prev = 0
    for start, end, emote_id in replacements:
        if start > prev:
            parts.append(_html.escape(message[prev:start]))
        url      = _TWITCH_CDN.format(id=emote_id)
        alt_text = _html.escape(message[start:end + 1])
        parts.append(
            f'<img class="chat-emote" src="{url}" alt="{alt_text}" title="{alt_text}">'
        )
        prev = end + 1
    if prev < len(message):
        parts.append(_html.escape(message[prev:]))
    return "".join(parts)


TWITCH_API_BASE = "https://api.twitch.tv/helix"


class TwitchService:
    def __init__(self, client_id: str, channel: str, supabase_url: str = "", supabase_anon_key: str = ""):
        self.client_id = client_id
        self.channel = channel.lower().lstrip("#")
        self._supabase_url      = supabase_url.rstrip("/")
        self._supabase_anon_key = supabase_anon_key
        # Token de usuário obtido via OAuth (Authorization Code Flow)
        # Vazio = conexão anônima (justinfan), que permite leitura do chat
        self._user_token: str = ""
        self._user_nick:  str = "justinfan12345"
        self._app_token: Optional[str] = None
        self._chat_task: Optional[asyncio.Task] = None
        self._on_message: Optional[Callable] = None
        self._connected = False
        self._ws = None  # active IRC WebSocket (for send_message)

    def set_user_token(self, token: str, nick: str = ""):
        """
        Atualiza o User Access Token obtido via OAuth.
        Se token estiver vazio, volta para conexão anônima.
        Reinicia o chat se já estiver conectado.
        """
        was_running = self._chat_task and not self._chat_task.done()
        callback = self._on_message

        self._user_token = token
        self._user_nick  = nick or "justinfan12345"

        if was_running and callback:
            self.stop_chat()
            self.start_chat(callback)

    # ------------------------------------------------------------------ #
    # OAuth App Token                                                       #
    # ------------------------------------------------------------------ #

    async def _get_app_token(self) -> str:
        """Obtain or return cached OAuth app token via Supabase Edge Function."""
        if self._app_token:
            return self._app_token
        fn_url = f"{self._supabase_url}/functions/v1/twitch-token"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                fn_url,
                json={},
                headers={"Authorization": f"Bearer {self._supabase_anon_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            self._app_token = resp.json()["access_token"]
            return self._app_token

    # ------------------------------------------------------------------ #
    # Stream Detection                                                      #
    # ------------------------------------------------------------------ #

    async def get_stream_info(self) -> Optional[dict]:
        """
        Return stream info dict if the channel is live, else None.
        Dict keys: id, title, viewer_count, thumbnail_url, game_name
        """
        if not self.client_id or not self._supabase_url or not self.channel:
            return None
        try:
            token = await self._get_app_token()
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{TWITCH_API_BASE}/streams",
                    params={"user_login": self.channel},
                    headers={
                        "Client-ID": self.client_id,
                        "Authorization": f"Bearer {token}",
                    },
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
                if data:
                    stream = data[0]
                    return {
                        "id": stream["id"],
                        "title": stream["title"],
                        "viewer_count": stream["viewer_count"],
                        "thumbnail_url": stream["thumbnail_url"],
                        "game_name": stream.get("game_name", ""),
                        "started_at": stream.get("started_at"),
                    }
        except Exception as e:
            logger.error(f"Twitch stream check failed: {e}")
        return None

    # ------------------------------------------------------------------ #
    # IRC Chat                                                              #
    # ------------------------------------------------------------------ #

    async def _irc_loop(self):
        """Connect to Twitch IRC and relay chat messages."""
        channel = f"#{self.channel}"

        while True:
            # Lê token/nick a cada reconexão para capturar atualizações via set_user_token()
            if self._user_token:
                token = f"oauth:{self._user_token}"
                nick  = self._user_nick
            else:
                token = "SCHMOOPIIE"
                nick  = "justinfan12345"

            try:
                async with websockets.connect(TWITCH_IRC_URL) as ws:
                    self._ws = ws
                    self._connected = True
                    logger.info(f"[Twitch IRC] Conectado – entrando em {channel}")
                    await ws.send(f"PASS {token}\r\n")
                    await ws.send(f"NICK {nick}\r\n")
                    await ws.send(f"CAP REQ :twitch.tv/tags twitch.tv/commands\r\n")
                    await ws.send(f"JOIN {channel}\r\n")

                    async for raw in ws:
                        await self._handle_irc(ws, raw)

            except asyncio.CancelledError:
                logger.info("[Twitch IRC] Task cancelada")
                break
            except Exception as e:
                logger.warning(f"[Twitch IRC] Reconectando em 5s ({e})")
                self._connected = False
                self._ws = None
                await asyncio.sleep(5)

        self._connected = False
        self._ws = None

    async def _handle_irc(self, ws, raw: str):
        """Parse an IRC line and fire the message callback."""
        # O servidor Twitch envia PING em nível IRC (texto), não WebSocket frames.
        # É obrigatório responder com PONG, caso contrário a conexão é derrubada.
        if raw.startswith("PING"):
            pong = raw.replace("PING", "PONG", 1)
            await ws.send(pong)
            return

        for line in raw.strip().split("\r\n"):
            if "PRIVMSG" not in line:
                continue
            try:
                # Parse tags
                tags: dict = {}
                if line.startswith("@"):
                    tag_str, line = line[1:].split(" ", 1)
                    for part in tag_str.split(";"):
                        if "=" in part:
                            k, v = part.split("=", 1)
                            tags[k] = v

                # Parse prefix and command
                # :user!user@user.tmi.twitch.tv PRIVMSG #channel :message
                parts = line.split(" ", 3)
                if len(parts) < 4:
                    continue
                user = parts[0].lstrip(":").split("!")[0]
                message = parts[3].lstrip(":")

                color = tags.get("color", "#9B9B9B") or "#9B9B9B"
                badges_raw = tags.get("badges", "")
                badges = [b.split("/")[0] for b in badges_raw.split(",") if b]
                emotes_tag   = tags.get("emotes", "")
                message_html = _build_twitch_html(message, emotes_tag)
                if emotes_tag:
                    logger.info(f"[Twitch Emotes] tag={emotes_tag!r} → html={message_html[:120]!r}")
                first_time = tags.get("first-msg") == "1"

                if self._on_message:
                    await self._on_message({
                        "platform":     "twitch",
                        "user":         user,
                        "message":      message,
                        "message_html": message_html,
                        "color":        color,
                        "badges":       badges,
                        "first_time":   first_time,
                    })
            except Exception as e:
                logger.debug(f"[Twitch IRC] Parse error: {e} — raw: {line!r}")

    async def send_message(self, text: str) -> bool:
        """Send a chat message to the channel via IRC PRIVMSG (requires user OAuth token)."""
        if not self._ws or not self._user_token:
            logger.debug("[Twitch IRC] send_message ignorado: sem token OAuth ou WS desconectado")
            return False
        try:
            await self._ws.send(f"PRIVMSG #{self.channel} :{text}\r\n")
            return True
        except Exception as e:
            logger.warning(f"[Twitch IRC] Falha ao enviar mensagem: {e}")
            return False

    async def create_clip(self) -> Optional[str]:
        """Create a clip of the current stream. Returns clip URL or None."""
        if not self._user_token or not self.client_id:
            return None
        try:
            # Get broadcaster ID first
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{TWITCH_API_BASE}/users",
                    params={"login": self.channel},
                    headers={"Client-ID": self.client_id, "Authorization": f"Bearer {self._user_token}"},
                )
                data = r.json().get("data", [])
                if not data:
                    return None
                broadcaster_id = data[0]["id"]

                r2 = await client.post(
                    f"{TWITCH_API_BASE}/clips",
                    params={"broadcaster_id": broadcaster_id},
                    headers={"Client-ID": self.client_id, "Authorization": f"Bearer {self._user_token}"},
                )
                clip_data = r2.json().get("data", [])
                if clip_data:
                    clip_id  = clip_data[0]["id"]
                    return f"https://clips.twitch.tv/{clip_id}"
        except Exception as e:
            logger.warning(f"[Twitch] Falha ao criar clip: {e}")
        return None

    def start_chat(self, on_message: Callable):
        """Start the IRC chat listener as a background asyncio task."""
        if self._chat_task and not self._chat_task.done():
            return
        self._on_message = on_message
        self._chat_task = asyncio.create_task(self._irc_loop())
        logger.info(f"[Twitch] Chat listener started for #{self.channel}")

    def stop_chat(self):
        if self._chat_task:
            self._chat_task.cancel()
            self._chat_task = None
        self._connected = False

    @property
    def chat_connected(self) -> bool:
        return self._connected
