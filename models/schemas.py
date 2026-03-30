from pydantic import BaseModel
from typing import Optional


class StreamStatus(BaseModel):
    youtube_live: bool = False
    twitch_live: bool = False
    kick_live: bool = False
    youtube_video_id: Optional[str] = None
    youtube_live_chat_id: Optional[str] = None
    twitch_stream_id: Optional[str] = None
    kick_stream_id: Optional[str] = None
    twitch_viewers: int = 0
    youtube_viewers: int = 0
    kick_viewers: int = 0
    twitch_live_since: Optional[str] = None   # ISO 8601 UTC
    youtube_live_since: Optional[str] = None  # ISO 8601 UTC
    kick_live_since: Optional[str] = None     # ISO 8601 UTC
    twitch_title: Optional[str] = None
    twitch_game: Optional[str] = None
    youtube_title: Optional[str] = None
    kick_title: Optional[str] = None
    twitch_channel: Optional[str] = None
    youtube_stream_id: Optional[str] = None   # video ID para montar URL watch?v=
    kick_channel: Optional[str] = None


class MusicInfo(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    player: Optional[str] = None
    thumbnail: Optional[str] = None  # base64 data URL or http URL
    duration: int = 0    # seconds
    position: int = 0    # seconds
    is_playing: bool = False


class ChatMessage(BaseModel):
    platform: str          # "twitch" | "youtube" | "kick"
    user: str
    message: str
    message_html: Optional[str] = None   # HTML com emotes renderizados
    color: Optional[str] = None
    badges: list[str] = []
    first_time: bool = False             # primeira mensagem no canal (Twitch: tag first-msg)
