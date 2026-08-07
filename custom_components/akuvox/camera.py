"""Camera platform for akuvox."""

from collections.abc import Callable, Awaitable

from homeassistant.helpers import storage
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.camera import Camera
from homeassistant.const import ATTR_IDENTIFIERS, CONF_NAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
from homeassistant.components.generic.camera import GenericCamera

from .const import DOMAIN, LOGGER, NAME, VERSION, DATA_STORAGE_KEY


async def async_setup_entry(hass: HomeAssistant,
                            _entry,
                            async_add_devices: Callable[[list], Awaitable[None]]):
    """Set up the camera platform."""
    store = storage.Store(hass, 1, DATA_STORAGE_KEY)
    device_data = await store.async_load()

    entities = []

    cameras_data = device_data.get("camera_data") if device_data else None
    if cameras_data:
        for camera_data in cameras_data:
            name = str(camera_data["name"]).strip()
            rtsp_url = str(camera_data["video_url"]).strip()
            entities.append(AkuvoxCameraEntity(
                hass=hass,
                name=name,
                rtsp_url=rtsp_url
            ))
    else:
        LOGGER.debug("No camera data found in device data")

    if async_add_devices is None:
        LOGGER.error("async_add_devices is None")
        return

    async_add_devices(entities)

    # Per-entry door log cameras - full-size screenshot for each log entry
    manager = AkuvoxDoorLogCameraManager(hass=hass, async_add_devices=async_add_devices)
    await manager.initialize()

    return True

async def async_unload_entry(hass: HomeAssistant, entry):
    """Unload camera platform and remove event listeners."""
    unsubs = hass.data.get(DOMAIN, {}).get("door_log_unsubs", [])
    for unsub in unsubs:
        unsub()
    hass.data[DOMAIN].pop("door_log_unsubs", None)
    return True

class AkuvoxCameraEntity(GenericCamera):
    """Akuvox camera class."""

    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        rtsp_url: str) -> None:
        """Initialize the Akuvox camera class."""
        LOGGER.debug("Adding Akuvox camera '%s'", name)

        super().__init__(
            hass=hass,
            device_info={
                ATTR_IDENTIFIERS: {(DOMAIN, name)},
                CONF_NAME: name,
                "stream_source": rtsp_url,
                "content_type": "",
                "limit_refetch_to_url_change": True,
                "advanced": {
                    "framerate": 2,
                    CONF_VERIFY_SSL: False,
                    "rtsp_transport": "udp",
                }
            },
            identifier=name,
            title=name,
        )

        self._name = name
        self._rtsp_url = rtsp_url
        self._attr_unique_id = name
        self._attr_name = name

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, name)},
            name=name,
            model=VERSION,
            manufacturer=NAME,
        )

class AkuvoxDoorLogEntryCamera(Camera):
    """One door log entry as a camera showing the full screenshot."""

    def __init__(self, hass: HomeAssistant, log_entry: dict, rank: int) -> None:
        """Initialize one door log entry camera."""
        super().__init__()
        self.hass = hass
        self._log_entry = log_entry
        self._rank = rank
        capture_time = log_entry.get("capture_time", "")
        self._attr_unique_id = f"Door Log Camera {capture_time}"
        self._attr_name = self._build_name()
        self._attr_icon = "mdi:door"
        self._attr_should_poll = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "Door Log")},  # type: ignore
            name="Door Log",
            model=VERSION,
            manufacturer=NAME,
        )

    def _build_name(self) -> str:
        """Name with zero-padded rank so HA sorts newest first."""
        return f"Door Log {self._rank:03d}"

    def update_data(self, log_entry: dict, rank: int):
        """Update this camera with the latest entry data."""
        self._log_entry = log_entry
        self._rank = rank
        self._attr_name = self._build_name()

    @property
    def state(self):
        """Return date/time, door and initiator as the state."""
        capture_time = self._log_entry.get("capture_time") or "?"
        location = self._log_entry.get("location") or "?"
        initiator = self._log_entry.get("initiator") or "?"
        return f"{capture_time} | {location} | {initiator}"

    def _local_path(self):
        """Resolve the local screenshot file path for this entry."""
        local_pic_url = self._log_entry.get("local_pic_url", "")
        if not local_pic_url:
            return None
        return self.hass.config.path(local_pic_url.replace("/local/", "www/", 1))

    async def async_camera_image(self, width: int | None = None,
                                 height: int | None = None):
        """Return this entry's screenshot as image bytes."""
        file_path = self._local_path()
        if not file_path:
            return None
        return await self.hass.async_add_executor_job(self._read_image, file_path)

    def _read_image(self, file_path):
        """Read image bytes from disk."""
        try:
            with open(file_path, "rb") as image_file:
                return image_file.read()
        except OSError as error:
            LOGGER.debug("Unable to read door log screenshot %s: %s", file_path, error)
            return None

class AkuvoxDoorLogCameraManager:
    """Creates and keeps per-entry door log cameras in sync with storage."""

    MAX_ENTRY_CAMERAS = 500

    def __init__(self, hass: HomeAssistant, async_add_devices) -> None:
        """Initialize the door log entry camera manager."""
        self.hass = hass
        self.async_add_devices = async_add_devices
        self._store = storage.Store(hass, 1, DATA_STORAGE_KEY)
        self.entities: dict = {}

    async def initialize(self):
        """Create cameras for existing entries and subscribe to updates."""
        try:
            await self.async_sync_cameras()
        except Exception as error:  # pylint: disable=broad-except
            LOGGER.error("❌ Error creating door log cameras on setup: %s", error)
        unsub = self.hass.bus.async_listen(
            "akuvox_door_log_updated", self._handle_door_log_updated)
        hass_data = self.hass.data.setdefault(DOMAIN, {})
        hass_data.setdefault("door_log_unsubs", []).append(unsub)

    async def _handle_door_log_updated(self, event):
        """Sync entry cameras when the poller detects new logs."""
        try:
            await self.async_sync_cameras()
        except Exception as error:  # pylint: disable=broad-except
            LOGGER.error("❌ Error syncing door log cameras: %s", error)

    async def async_sync_cameras(self):
        """Create/update entry cameras from the stored door log list."""
        stored_data: dict = await self._store.async_load() # type: ignore
        entries = []
        if stored_data:
            entries = [entry for entry in stored_data.get("door_log_entries", [])
                       if isinstance(entry, dict)]
        LOGGER.debug("📷 Door log camera sync: %s entries in storage", len(entries))
        entries = entries[:self.MAX_ENTRY_CAMERAS]

        new_entities = []
        for rank, log_entry in enumerate(entries, start=1):
            key = str(log_entry.get("capture_time", ""))
            if not key:
                continue
            if key in self.entities:
                self.entities[key].update_data(log_entry, rank)
            else:
                camera = AkuvoxDoorLogEntryCamera(
                    hass=self.hass, log_entry=log_entry, rank=rank)
                self.entities[key] = camera
                new_entities.append(camera)
        if new_entities:
            self.async_add_devices(new_entities)

