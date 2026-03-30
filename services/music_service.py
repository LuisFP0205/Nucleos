"""
Music detector using the Windows Global System Media Transport Controls API.
Supports Spotify, VLC, Chrome/Edge browsers, and any Windows media player.

Requires: pip install winsdk
"""
import asyncio
import base64
import logging
from typing import Optional
from models.schemas import MusicInfo

logger = logging.getLogger(__name__)


async def _get_thumbnail_base64(session) -> Optional[str]:
    """Read the album thumbnail stream and return a base64 data URL."""
    try:
        props = await session.try_get_media_properties_async()
        thumb_ref = props.thumbnail
        if not thumb_ref:
            return None

        stream = await thumb_ref.open_read_async()
        size = stream.size
        if not size:
            return None

        reader_type = None
        try:
            from winsdk.windows.storage.streams import DataReader
            reader_type = DataReader
        except ImportError:
            return None

        reader = reader_type(stream)
        await reader.load_async(size)
        buf = bytearray(size)
        reader.read_bytes(buf)
        b64 = base64.b64encode(bytes(buf)).decode("utf-8")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        logger.debug(f"Thumbnail read error: {e}")
        return None


async def get_all_sessions() -> list:
    """Return a list of all active GSMTC media sessions."""
    try:
        from winsdk.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as MediaManager,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
        )
        sessions_manager = await MediaManager.request_async()
        sessions = sessions_manager.get_sessions()
        result = []
        for session in sessions:
            try:
                props = await session.try_get_media_properties_async()
                playback = session.get_playback_info()
                status = playback.playback_status if playback else None
                is_playing = status == PlaybackStatus.PLAYING if status is not None else False
                source_id = session.source_app_user_model_id or ""
                result.append({
                    "source_id": source_id,
                    "player": _player_name_from_source(source_id),
                    "title": props.title or "",
                    "is_playing": is_playing,
                })
            except Exception:
                pass
        return result
    except Exception as e:
        logger.error(f"[Music] get_all_sessions error: {e}")
        return []


async def get_media_for_player(source_id: str) -> MusicInfo:
    """Get media info for a specific player by source_app_user_model_id."""
    try:
        from winsdk.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as MediaManager,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
        )
        sessions_manager = await MediaManager.request_async()
        sessions = sessions_manager.get_sessions()

        target = None
        for session in sessions:
            if session.source_app_user_model_id == source_id:
                target = session
                break

        if not target:
            return MusicInfo()

        props = await target.try_get_media_properties_async()
        playback = target.get_playback_info()
        timeline = target.get_timeline_properties()

        title = props.title or ""
        artist = props.artist or ""
        album = props.album_title or ""
        player = _player_name_from_source(source_id)

        status = playback.playback_status if playback else None
        is_playing = status == PlaybackStatus.PLAYING if status is not None else False

        duration = 0
        position = 0
        if timeline:
            try:
                duration = int(timeline.end_time.duration / 10_000_000)
                position = int(timeline.position.duration / 10_000_000)
            except Exception:
                pass

        thumbnail = await _get_thumbnail_base64(target)

        return MusicInfo(
            title=title, artist=artist, album=album, player=player,
            thumbnail=thumbnail, duration=duration, position=position,
            is_playing=is_playing,
        )
    except Exception as e:
        logger.error(f"[Music] get_media_for_player error: {e}")
        return MusicInfo()


async def get_current_media() -> MusicInfo:
    """
    Query the Windows GSMTC API for the currently playing media session.
    Returns a MusicInfo object (empty fields if nothing is playing).
    """
    try:
        from winsdk.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as MediaManager,
        )
        from winsdk.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
        )

        sessions_manager = await MediaManager.request_async()
        current = sessions_manager.get_current_session()

        if not current:
            return MusicInfo()

        # Media properties
        props = await current.try_get_media_properties_async()
        playback = current.get_playback_info()
        timeline = current.get_timeline_properties()

        title = props.title or ""
        artist = props.artist or ""
        album = props.album_title or ""

        # Source app identifier (e.g. "Spotify.exe", "chrome.exe")
        source_id = current.source_app_user_model_id or ""
        player = _player_name_from_source(source_id)

        # Playback state
        status = playback.playback_status if playback else None
        is_playing = status == PlaybackStatus.PLAYING if status is not None else False

        # Timeline
        duration = 0
        position = 0
        if timeline:
            try:
                duration = int(timeline.end_time.duration / 10_000_000)
                position = int(timeline.position.duration / 10_000_000)
            except Exception:
                pass

        # Thumbnail
        thumbnail = await _get_thumbnail_base64(current)

        return MusicInfo(
            title=title,
            artist=artist,
            album=album,
            player=player,
            thumbnail=thumbnail,
            duration=duration,
            position=position,
            is_playing=is_playing,
        )

    except ImportError:
        logger.warning("winsdk not installed. Run: pip install winsdk")
        return MusicInfo()
    except Exception as e:
        logger.error(f"Music detection error: {e}")
        return MusicInfo()


def _player_name_from_source(source_id: str) -> str:
    """Map Windows app user model ID to a friendly player name."""
    source_lower = source_id.lower()
    if "spotify" in source_lower:
        return "Spotify"
    if "vlc" in source_lower:
        return "VLC"
    if "chrome" in source_lower:
        return "Chrome"
    if "msedge" in source_lower or "edge" in source_lower:
        return "Edge"
    if "firefox" in source_lower:
        return "Firefox"
    if "foobar" in source_lower:
        return "foobar2000"
    if "musicbee" in source_lower:
        return "MusicBee"
    if "winamp" in source_lower:
        return "Winamp"
    if source_id:
        # Return last segment of the ID as a fallback
        return source_id.split("!")[-1].split(".")[0].capitalize()
    return "Unknown"
