"""
Feature 14 – Real-time chat via WebSocket.
WS  ws://localhost:3000/ws/chat   ← overlays connect here
GET /chat/history                 ← last N messages (REST fallback)
"""
import asyncio
import csv
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from models.schemas import ChatMessage

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

# ------------------------------------------------------------------ #
# History — persisted to disk, limit varies by plan                   #
# ------------------------------------------------------------------ #

_HISTORY_FILE = Path("chat_history.json")
_LIMIT_FREE    = 50
_LIMIT_PREMIUM = 100

_history: list[dict] = []
_max_history: int = _LIMIT_FREE  # default FREE até o plano ser informado


def _load_history() -> list[dict]:
    try:
        data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            # Carrega no máximo o limite Premium (valor mais alto possível)
            return data[-_LIMIT_PREMIUM:]
    except Exception:
        pass
    return []


def _save_history() -> None:
    try:
        _HISTORY_FILE.write_text(
            json.dumps(_history, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"[Chat] Falha ao salvar histórico: {e}")


def set_history_limit(is_premium: bool) -> None:
    """Chamado por auth_supabase quando o plano do usuário é informado."""
    global _max_history, _history
    _max_history = _LIMIT_PREMIUM if is_premium else _LIMIT_FREE
    # Aplica o limite imediatamente se o histórico atual exceder
    if len(_history) > _max_history:
        _history = _history[-_max_history:]
        _save_history()
    logger.info(f"[Chat] Limite do histórico definido: {_max_history} mensagens ({'Premium' if is_premium else 'FREE'})")


# Carrega histórico do disco ao iniciar
_history = _load_history()
logger.info(f"[Chat] Histórico carregado: {len(_history)} mensagens de {_HISTORY_FILE}")


# ------------------------------------------------------------------ #
# Connection Manager                                                   #
# ------------------------------------------------------------------ #

_command_handler = None  # Optional[Callable] — set from main.py


def set_command_handler(fn) -> None:
    global _command_handler
    _command_handler = fn


class ChatManager:
    def __init__(self):
        self._clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.append(ws)
        logger.info(f"[WS] Client connected (total={len(self._clients)})")
        # Envia histórico ao novo cliente
        for msg in _history:
            try:
                await ws.send_json(msg)
            except Exception:
                break

    def disconnect(self, ws: WebSocket):
        if ws in self._clients:
            self._clients.remove(ws)
        logger.info(f"[WS] Client disconnected (total={len(self._clients)})")

    async def broadcast(self, message: dict):
        """Envia mensagem a todos os clientes WebSocket e persiste no histórico."""
        global _history
        _history.append(message)
        # Garante que nunca ultrapasse o limite do plano
        if len(_history) > _max_history:
            del _history[0]
        _save_history()

        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def on_message(self, msg: dict):
        """Callback usado pelos serviços Twitch/YouTube/Kick."""
        if not _platform_enabled.get(msg.get("platform", ""), True):
            return
        await self.broadcast(msg)
        # Command processing (fire-and-forget, never blocks broadcast)
        if _command_handler:
            asyncio.create_task(_command_handler(msg))


# Singleton usado em todo o app
chat_manager = ChatManager()

# Quais plataformas podem transmitir mensagens
_platform_enabled: dict[str, bool] = {"twitch": True, "youtube": True, "kick": True}


def set_platform_enabled(platform: str, enabled: bool) -> None:
    _platform_enabled[platform] = enabled


async def broadcast(message: dict):
    if not _platform_enabled.get(message.get("platform", ""), True):
        return
    await chat_manager.broadcast(message)


# ------------------------------------------------------------------ #
# WebSocket endpoint                                                   #
# ------------------------------------------------------------------ #

@router.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    await chat_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        chat_manager.disconnect(ws)
    except Exception:
        chat_manager.disconnect(ws)


# ------------------------------------------------------------------ #
# REST fallback: últimas N mensagens                                   #
# ------------------------------------------------------------------ #

@router.get("/chat/history")
async def chat_history():
    return list(_history)


@router.get("/chat/export")
async def chat_export(
    format: str = Query("txt", pattern="^(txt|csv)$"),
    is_premium: bool = Query(False),
):
    limit   = _LIMIT_PREMIUM if is_premium else _LIMIT_FREE
    msgs    = list(_history)[-limit:]
    ts_now  = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname   = f"chat_{ts_now}.{format}"

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["plataforma", "usuario", "mensagem"])
        for m in msgs:
            writer.writerow([m.get("platform", ""), m.get("user", ""), m.get("message", "")])
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )

    # txt
    lines = [f"[{m.get('platform','?')}] {m.get('user','?')}: {m.get('message','')}" for m in msgs]
    content = "\n".join(lines)
    return StreamingResponse(
        iter([content]),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
