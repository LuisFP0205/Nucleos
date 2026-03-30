"""
Feature 13 – Advanced music detector.

GET  /music/current   →  MusicInfo JSON (auto ou player fixado)
GET  /music/players   →  lista de sessões GSMTC ativas
POST /music/select    →  fixa um player ou volta ao auto-detect
GET  /music/settings  →  retorna estado atual (auto, pinned)
"""
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from models.schemas import MusicInfo
from services.music_service import get_current_media, get_all_sessions, get_media_for_player

router = APIRouter(prefix="/music", tags=["music"])

# Estado em memória
_auto_detect: bool = True
_pinned_player: Optional[str] = None


class SelectPlayerRequest(BaseModel):
    source_id: Optional[str] = None
    auto: bool = True


@router.get("/current", response_model=MusicInfo)
async def current_music():
    """Retorna a mídia em reprodução (auto-detect ou player fixado)."""
    if _auto_detect or not _pinned_player:
        return await get_current_media()
    return await get_media_for_player(_pinned_player)


@router.get("/players")
async def list_players():
    """Retorna todas as sessões de mídia ativas no Windows."""
    return await get_all_sessions()


@router.get("/settings")
async def music_settings():
    """Retorna o estado atual do auto-detect e do player fixado."""
    return {"auto": _auto_detect, "pinned": _pinned_player}


@router.post("/select")
async def select_player(req: SelectPlayerRequest):
    """Fixa um player específico ou reativa o auto-detect."""
    global _auto_detect, _pinned_player
    _auto_detect = req.auto
    _pinned_player = None if req.auto else req.source_id
    return {"auto": _auto_detect, "pinned": _pinned_player}
