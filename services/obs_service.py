"""
OBS WebSocket 5.x integration.

Uses obsws-python (ReqClient) wrapped in asyncio.run_in_executor so it
never blocks the FastAPI event loop.
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class OBSService:
    def __init__(self, host: str = "localhost", port: int = 4455, password: str = ""):
        self.host = host
        self.port = port
        self.password = password
        self._client = None
        self._connected = False

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    async def _run(self, fn):
        """Run a blocking obsws-python call in a thread executor."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, fn)

    def _make_client(self):
        import obsws_python as obs  # lazy import — optional dependency
        return obs.ReqClient(
            host=self.host,
            port=self.port,
            password=self.password,
            timeout=3,
        )

    # ------------------------------------------------------------------ #
    # Connection management                                                #
    # ------------------------------------------------------------------ #

    async def connect(self) -> bool:
        """(Re)connect to OBS WebSocket. Returns True on success."""
        try:
            def _connect():
                self._client = self._make_client()

            await self._run(_connect)
            self._connected = True
            logger.info(f"[OBS] Connected → ws://{self.host}:{self.port}")
            return True
        except Exception as e:
            self._connected = False
            self._client = None
            logger.warning(f"[OBS] Connection failed: {e}")
            return False

    async def disconnect(self):
        if self._client:
            try:
                def _disc():
                    self._client.disconnect()
                await self._run(_disc)
            except Exception:
                pass
        self._client = None
        self._connected = False
        logger.info("[OBS] Disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------ #
    # Status                                                               #
    # ------------------------------------------------------------------ #

    async def get_status(self) -> dict:
        """Returns connection + current scene + streaming/recording state."""
        if not self._client:
            return {"connected": False}
        try:
            def _get():
                scene  = self._client.get_current_program_scene()
                stream = self._client.get_stream_status()
                record = self._client.get_record_status()
                scenes = self._client.get_scene_list()
                return scene, stream, record, scenes

            scene, stream, record, scenes = await self._run(_get)
            return {
                "connected":     True,
                "current_scene": scene.current_program_scene_name,
                "streaming":     stream.output_active,
                "recording":     record.output_active,
                "scenes":        [s["sceneName"] for s in scenes.scenes],
            }
        except Exception as e:
            self._connected = False
            logger.warning(f"[OBS] get_status failed: {e}")
            return {"connected": False, "error": str(e)}

    # ------------------------------------------------------------------ #
    # Scene control                                                        #
    # ------------------------------------------------------------------ #

    async def set_scene(self, scene_name: str) -> bool:
        if not self._client:
            return False
        try:
            def _set():
                self._client.set_current_program_scene(scene_name)
            await self._run(_set)
            logger.info(f"[OBS] Scene → '{scene_name}'")
            return True
        except Exception as e:
            logger.warning(f"[OBS] set_scene failed: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Source visibility                                                    #
    # ------------------------------------------------------------------ #

    async def get_sources(self, scene_name: str) -> list[dict]:
        """Returns [{name, id, visible}, ...] for every source in the scene."""
        if not self._client:
            return []
        try:
            def _get():
                items = self._client.get_scene_item_list(scene_name)
                return [
                    {
                        "name":    item["sourceName"],
                        "id":      item["sceneItemId"],
                        "visible": item["sceneItemEnabled"],
                    }
                    for item in items.scene_items
                ]
            return await self._run(_get)
        except Exception as e:
            logger.warning(f"[OBS] get_sources failed: {e}")
            return []

    async def set_source_visible(
        self, scene_name: str, source_name: str, visible: bool
    ) -> bool:
        if not self._client:
            return False
        try:
            def _set():
                items = self._client.get_scene_item_list(scene_name)
                for item in items.scene_items:
                    if item["sourceName"] == source_name:
                        self._client.set_scene_item_enabled(
                            scene_name, item["sceneItemId"], visible
                        )
                        return True
                return False

            result = await self._run(_set)
            if result:
                logger.info(
                    f"[OBS] Source '{source_name}' visible={visible} in '{scene_name}'"
                )
            return result
        except Exception as e:
            logger.warning(f"[OBS] set_source_visible failed: {e}")
            return False
