"""
Log streaming via WebSocket.
WS  /ws/logs  → transmite registros de log em tempo real
GET /logs     → página HTML do terminal de logs (sem link no UI)
"""
import logging
from collections import deque
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["logs"])

# Histórico dos últimos 500 registros (para exibir ao conectar)
_history: deque[str] = deque(maxlen=500)
_clients: set[WebSocket] = set()


class _WSLogHandler(logging.Handler):
    """Handler que captura registros e envia para os clientes WS."""

    def emit(self, record: logging.LogRecord):
        import asyncio
        line = self.format(record)
        _history.append(line)
        dead = set()
        for ws in _clients:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(ws.send_text(line))
            except Exception:
                dead.add(ws)
        _clients.difference_update(dead)


# Instala o handler no logger raiz uma única vez
_handler = _WSLogHandler()
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
logging.getLogger().addHandler(_handler)


@router.websocket("/ws/logs")
async def ws_logs(websocket: WebSocket):
    await websocket.accept()
    _clients.add(websocket)
    # Envia histórico ao conectar
    for line in list(_history):
        await websocket.send_text(line)
    try:
        while True:
            await websocket.receive_text()  # mantém conexão aberta
    except WebSocketDisconnect:
        _clients.discard(websocket)
