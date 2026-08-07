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

    # Door log camera - full-size screenshot of the newest door log entry
    entities.append(AkuvoxDoorLogCamera(hass=hass))

    if async_add_devices is None:
        LOGGER.error("async_add_devices is None")
        return

    async_add_devices(entities)
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

class AkuvoxDoorLogCamera(Camera):
    """Camera entity showing the newest door log screenshot (full size)."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the door log camera."""
        super().__init__()
        self.hass = hass
        self._store = storage.Store(hass, 1, DATA_STORAGE_KEY)
        self._attr_unique_id = "Door Log Camera"
        self._attr_name = "Door Log Camera"
        self._attr_icon = "mdi:door"
        self._attr_should_poll = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "Door Log")},  # type: ignore
            name="Door Log",
            model=VERSION,
            manufacturer=NAME,
        )
        LOGGER.debug("Adding door log camera")

    async def async_camera_image(self, width: int | None = None,
                                 height: int | None = None):
        """Return the newest door log screenshot as image bytes."""
        stored_data: dict = await self._store.async_load() # type: ignore
        entries = []
        if stored_data:
            entries = [entry for entry in stored_data.get("door_log_entries", [])
                       if isinstance(entry, dict)]
        if not entries:
            return None
        local_pic_url = entries[0].get("local_pic_url", "")
        if not local_pic_url:
            return None
        file_path = self.hass.config.path(local_pic_url.replace("/local/", "", 1))
        return await self.hass.async_add_executor_job(self._read_image, file_path)

    def _read_image(self, file_path):
        """Read image bytes from disk."""
        try:
            with open(file_path, "rb") as image_file:
                return image_file.read()
        except OSError as error:
            LOGGER.debug("Unable to read door log screenshot %s: %s", file_path, error)
            return None

