"""
YouTube service: live stream auto-detection + live chat polling.

Detecção de live usa RSS + videos.list (1 unidade/chamada)
em vez de search (100 unidades/chamada) para evitar quota exceeded.

Custo estimado: ~2.880 unidades/dia (30s de intervalo)
Limite da API:  10.000 unidades/dia
"""
import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Callable, Optional
import httpx

logger = logging.getLogger(__name__)

YT_API_BASE  = "https://www.googleapis.com/youtube/v3"
YT_RSS_BASE  = "https://www.youtube.com/feeds/videos.xml"
RSS_NS       = "http://www.youtube.com/xml/schemas/2015"

_QUOTA_ERRORS  = {"quotaExceeded", "rateLimitExceeded", "userRateLimitExceeded"}
_CONFIG_ERRORS = {
    "keyInvalid":          "API Key inválida. Verifique YOUTUBE_API_KEY no .env",
    "keyExpired":          "API Key expirada. Gere uma nova no Google Cloud Console",
    "accessNotConfigured": (
        "YouTube Data API v3 não está ativada.\n"
        "  → console.cloud.google.com → APIs e Serviços → Biblioteca\n"
        "  → Ative: 'YouTube Data API v3'"
    ),
    "forbidden": "Acesso negado. Verifique as restrições da API Key.",
}


def _parse_yt_error(resp: httpx.Response) -> tuple[str, str]:
    try:
        body   = resp.json()
        errors = body.get("error", {}).get("errors", [{}])
        reason = errors[0].get("reason", "unknown")
        msg    = errors[0].get("message", body.get("error", {}).get("message", ""))
        return reason, msg
    except Exception:
        return "unknown", resp.text[:300]


class YouTubeService:
    def __init__(self, channel_id: str, supabase_url: str = "", supabase_anon_key: str = ""):
        self.channel_id         = channel_id
        self._supabase_url      = supabase_url.rstrip("/")
        self._supabase_anon_key = supabase_anon_key
        self._chat_task:    Optional[asyncio.Task] = None
        self._on_message:   Optional[Callable]     = None
        self._connected     = False
        self._api_blocked   = False
        self._oauth_token:  Optional[str] = None   # set via set_oauth_token()
        self._live_chat_id: Optional[str] = None   # updated when start_chat() is called

    async def _yt_api_get(self, endpoint: str, params: dict) -> httpx.Response:
        """Chama YouTube Data API via Supabase Edge Function (sem expor a API key)."""
        fn_url = f"{self._supabase_url}/functions/v1/youtube-data"
        async with httpx.AsyncClient() as client:
            return await client.get(
                fn_url,
                params={"endpoint": endpoint, **params},
                headers={"Authorization": f"Bearer {self._supabase_anon_key}"},
                timeout=10,
            )

    # ------------------------------------------------------------------ #
    # Stream Detection (RSS + videos.list — custo: 1 unidade/chamada)     #
    # ------------------------------------------------------------------ #

    async def _get_recent_video_ids(self) -> list[str]:
        """
        Busca os IDs dos últimos vídeos/lives do canal via RSS (gratuito, sem cota).
        Retorna até 5 IDs para checar.
        """
        url = f"{YT_RSS_BASE}?channel_id={self.channel_id}"
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=10)
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        ns   = {"atom": "http://www.w3.org/2005/Atom", "yt": RSS_NS}
        ids  = [
            entry.find("yt:videoId", ns).text
            for entry in root.findall("atom:entry", ns)
            if entry.find("yt:videoId", ns) is not None
        ]
        return ids[:5]

    async def _get_active_live_via_oauth(self) -> Optional[dict]:
        """
        Detecta live ativa usando OAuth (mine=true) — funciona com lives não listadas.
        Custo: 1 unidade de API. Requer OAuth token.
        """
        if not self._oauth_token:
            return None
        try:
            async with httpx.AsyncClient() as client:
                # Busca lives ativas do próprio canal autenticado
                resp = await client.get(
                    f"{YT_API_BASE}/liveBroadcasts",
                    params={
                        "part":          "id,snippet,status",
                        "broadcastType": "all",
                        "mine":          "true",
                        "maxResults":    10,
                    },
                    headers={"Authorization": f"Bearer {self._oauth_token}"},
                    timeout=10,
                )
                if resp.status_code != 200:
                    logger.debug(f"[YouTube OAuth] liveBroadcasts {resp.status_code}: {resp.text[:200]}")
                    return None

                # Filtra apenas broadcasts ao vivo agora
                items = [
                    i for i in resp.json().get("items", [])
                    if i.get("status", {}).get("lifeCycleStatus") == "live"
                ]
                if not items:
                    return None

                broadcast_id = items[0]["id"]
                title        = items[0]["snippet"].get("title", "")

                # Busca liveChatId via videos.list
                resp2 = await self._yt_api_get("videos", {
                    "part": "liveStreamingDetails,snippet",
                    "id":   broadcast_id,
                })
                if resp2.status_code != 200:
                    return None

                for item in resp2.json().get("items", []):
                    details      = item.get("liveStreamingDetails", {})
                    live_chat_id = details.get("activeLiveChatId")
                    if not live_chat_id:
                        continue
                    logger.info(f"[YouTube] Live detectada via OAuth: {title} ({broadcast_id})")
                    return {
                        "video_id":     broadcast_id,
                        "live_chat_id": live_chat_id,
                        "title":        title,
                        "viewers":      int(details.get("concurrentViewers", 0)),
                        "started_at":   details.get("actualStartTime"),
                    }
        except Exception as e:
            logger.debug(f"[YouTube] OAuth live detection falhou: {e}")
        return None

    async def get_active_live(self) -> Optional[dict]:
        """
        Detecta live ativa.
        Prioridade: OAuth (suporta lives não listadas) → RSS + videos.list (públicas).
        """
        if not self.channel_id and not self._oauth_token:
            return None
        if self._api_blocked:
            return None

        # Tenta via OAuth primeiro (detecta lives não listadas)
        if self._oauth_token:
            result = await self._get_active_live_via_oauth()
            if result:
                return result

        if not self._supabase_url or not self.channel_id:
            return None

        try:
            video_ids = await self._get_recent_video_ids()
            if not video_ids:
                return None

            resp = await self._yt_api_get("videos", {
                "part": "liveStreamingDetails,snippet",
                "id":   ",".join(video_ids),
            })

            if resp.status_code == 403:
                reason, msg = _parse_yt_error(resp)
                if reason in _QUOTA_ERRORS:
                    logger.warning(
                        f"[YouTube] Cota excedida ({reason}). "
                        "Pausando 5 minutos antes de tentar novamente."
                    )
                    await asyncio.sleep(300)
                    return None
                hint = _CONFIG_ERRORS.get(reason, "Verifique as configurações da API Key.")
                logger.error(
                    f"[YouTube] Acesso negado (403) — reason={reason}\n"
                    f"  {msg}\n  {hint}"
                )
                self._api_blocked = True
                return None

            resp.raise_for_status()
            self._api_blocked = False

            for item in resp.json().get("items", []):
                details      = item.get("liveStreamingDetails", {})
                live_chat_id = details.get("activeLiveChatId")
                # activeLiveChatId só existe em streams ativas
                if not live_chat_id:
                    continue
                video_id = item["id"]
                title    = item["snippet"]["title"]
                logger.debug(f"[YouTube] Live ativa encontrada: {title} ({video_id})")
                return {
                    "video_id":     video_id,
                    "live_chat_id": live_chat_id,
                    "title":        title,
                    "viewers":      int(details.get("concurrentViewers", 0)),
                    "started_at":   details.get("actualStartTime"),
                }

        except httpx.HTTPStatusError as e:
            logger.error(f"[YouTube] Erro HTTP {e.response.status_code}: {e}")
        except ET.ParseError as e:
            logger.error(f"[YouTube] Erro ao parsear RSS: {e}")
        except Exception as e:
            logger.error(f"[YouTube] Erro inesperado na detecção: {e}")

        return None

    # ------------------------------------------------------------------ #
    # Live Chat Polling                                                     #
    # ------------------------------------------------------------------ #

    async def _chat_loop(self, live_chat_id: str):
        """Faz polling do chat da live e dispara callbacks de mensagem."""
        page_token: Optional[str] = None
        poll_interval = 5

        while True:
            try:
                params: dict = {
                    "part":       "id,snippet,authorDetails",
                    "liveChatId": live_chat_id,
                    "maxResults": 200,
                }
                if page_token:
                    params["pageToken"] = page_token

                # OAuth tem prioridade — necessário para lives não listadas
                if self._oauth_token:
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(
                            f"{YT_API_BASE}/liveChat/messages",
                            params=params,
                            headers={"Authorization": f"Bearer {self._oauth_token}"},
                            timeout=10,
                        )
                else:
                    resp = await self._yt_api_get("liveChat/messages", params)

                    if resp.status_code == 403:
                        reason, msg = _parse_yt_error(resp)
                        if reason in _QUOTA_ERRORS:
                            logger.warning(f"[YouTube Chat] Cota excedida. Pausando 60s.")
                            await asyncio.sleep(60)
                            continue
                        hint = _CONFIG_ERRORS.get(reason, "")
                        logger.error(
                            f"[YouTube Chat] Acesso negado (403) — reason={reason}\n"
                            f"  {msg}\n" + (f"  {hint}" if hint else "")
                        )
                        break

                    if resp.status_code == 401 and self._oauth_token:
                        logger.warning("[YouTube Chat] Token expirado (401) — aguardando refresh")
                        await asyncio.sleep(15)
                        continue

                    resp.raise_for_status()
                    data = resp.json()

                poll_interval = max(3, data.get("pollingIntervalMillis", 5000) // 1000)
                page_token    = data.get("nextPageToken")
                self._connected = True

                for item in data.get("items", []):
                    snippet  = item.get("snippet", {})
                    author   = item.get("authorDetails", {})
                    if snippet.get("type") != "textMessageEvent":
                        continue
                    text     = snippet.get("textMessageDetails", {}).get("messageText", "")
                    username = author.get("displayName", "")

                    badges = []
                    if author.get("isChatOwner"):
                        badges.append("owner")
                    if author.get("isChatModerator"):
                        badges.append("moderator")

                    if self._on_message and text:
                        await self._on_message({
                            "platform": "youtube",
                            "user":     username,
                            "message":  text,
                            "color":    "#FF0000",
                            "badges":   badges,
                        })

                await asyncio.sleep(poll_interval)

            except asyncio.CancelledError:
                logger.info("[YouTube Chat] Task cancelada")
                break
            except Exception as e:
                logger.warning(f"[YouTube Chat] Erro, retentando em 10s: {e}")
                self._connected = False
                await asyncio.sleep(10)

        self._connected = False

    def set_oauth_token(self, token: str) -> None:
        """Set YouTube OAuth token to enable sending chat messages."""
        self._oauth_token = token

    async def send_message(self, text: str) -> bool:
        """Send a message to the active YouTube live chat (requires OAuth token)."""
        if not self._oauth_token or not self._live_chat_id:
            logger.debug("[YouTube Chat] send_message ignorado: sem OAuth token ou live_chat_id")
            return False
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{YT_API_BASE}/liveChat/messages?part=snippet",
                    headers={"Authorization": f"Bearer {self._oauth_token}"},
                    json={
                        "snippet": {
                            "liveChatId": self._live_chat_id,
                            "type": "textMessageEvent",
                            "textMessageDetails": {"messageText": text},
                        }
                    },
                    timeout=10,
                )
                if resp.status_code == 200:
                    return True
                logger.warning(f"[YouTube Chat] Falha ao enviar: {resp.status_code} {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"[YouTube Chat] Erro ao enviar mensagem: {e}")
        return False

    def start_chat(self, live_chat_id: str, on_message: Callable):
        if self._chat_task and not self._chat_task.done():
            return
        self._live_chat_id = live_chat_id
        self._on_message   = on_message
        self._chat_task    = asyncio.create_task(self._chat_loop(live_chat_id))
        logger.info(f"[YouTube] Chat polling iniciado (liveChatId={live_chat_id})")

    def stop_chat(self):
        if self._chat_task:
            self._chat_task.cancel()
            self._chat_task = None
        self._connected = False

    @property
    def chat_connected(self) -> bool:
        return self._connected
