"""Sensor platform for akuvox."""
from datetime import datetime
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers import storage
from homeassistant.helpers.entity import DeviceInfo

from .api import AkuvoxApiClient
from .coordinator import AkuvoxDataUpdateCoordinator
from .const import (
    DOMAIN,
    LOGGER,
    NAME,
    VERSION,
    DATA_STORAGE_KEY
)
from .entity import AkuvoxEntity

async def async_setup_entry(hass, entry, async_add_devices):
    """Set up the temporary door key platform."""
    coordinator: AkuvoxDataUpdateCoordinator
    for _key, value in hass.data[DOMAIN].items():
        coordinator = value
    client = coordinator.client
    store = storage.Store(hass, 1, DATA_STORAGE_KEY)
    device_data: dict = await store.async_load() # type: ignore

    entities = []

    if not device_data or "door_keys_data" not in device_data:
        LOGGER.error("No door keys data found")
    else:
        door_keys_data = device_data["door_keys_data"]
        date_format = "%d-%m-%Y %H:%M:%S"

        for door_key_data in door_keys_data:
            key_id = door_key_data["key_id"]
            description = door_key_data["description"]
            key_code=door_key_data["key_code"]
            begin_time = datetime.strptime(str(door_key_data["begin_time"]), date_format)
            end_time = datetime.strptime(str(door_key_data["end_time"]), date_format)
            allowed_times=door_key_data["allowed_times"]
            access_times=door_key_data["access_times"]
            qr_code_url=door_key_data["qr_code_url"]

            entities.append(
                AkuvoxTemporaryDoorKey(
                    client=client,
                    entry=entry,
                    key_id=key_id,
                    description=description,
                    key_code=key_code,
                    begin_time=begin_time,
                    end_time=end_time,
                    allowed_times=allowed_times,
                    access_times=access_times,
                    qr_code_url=qr_code_url,
                )
            )

    # Door log sensor (its own device) - list of recent door log entries
    entities.append(AkuvoxDoorLogSensor(client=client, entry=entry, store=store))

    async_add_devices(entities)

class AkuvoxTemporaryDoorKey(SensorEntity, AkuvoxEntity):
    """Akuvox temporary door key class."""

    def __init__(
        self,
        client: AkuvoxApiClient,
        entry,
        key_id: str,
        description: str,
        key_code: str,
        begin_time: datetime,
        end_time: datetime,
        allowed_times: int,
        access_times: int,
        qr_code_url) -> None:
        """Initialize the Akuvox door relay class."""
        super(SensorEntity, self).__init__(client=client, entry=entry)
        AkuvoxEntity.__init__(
            self=self,
            client=client,
            entry=entry
        )
        self.client = client
        self.key_id = key_id
        self.description = description
        self.key_code = key_code
        self.begin_time = begin_time
        self.end_time = end_time
        self.allowed_times = allowed_times
        self.access_times = access_times
        self.qr_code_url = qr_code_url
        self.expired = False

        name = f"{self.description} {self.key_id}".strip()
        self._attr_unique_id = name
        self._attr_name = name
        self._attr_key_code = key_code

        self._attr_extra_state_attributes = self.to_dict()

        LOGGER.debug("Adding temporary door key '%s'", self._attr_unique_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "Temporary Keys")},  # type: ignore
            name="Temporary Keys",
            model=VERSION,
            manufacturer=NAME,
        )

    def is_key_active(self):
        """Check if the key is currently active based on the begin_time and end_time."""
        current_time = datetime.now()
        return self.begin_time <= current_time <= self.end_time

    def to_dict(self):
        """Convert the object to a dictionary for easy serialization."""
        return {
            'key_id': self.key_id,
            'description': self.description,
            'key_code': self.key_code,
            'enabled': self.is_key_active(),
            'begin_time': self.begin_time,
            'end_time': self.end_time,
            'access_times': self.access_times,
            'allowed_times': self.allowed_times,
            'qr_code_url': self.qr_code_url,
            'expired': not self.is_key_active()
        }

class AkuvoxDoorLogSensor(SensorEntity, AkuvoxEntity):
    """Akuvox door log sensor - list of recent door log entries with screenshots."""

    def __init__(self, client: AkuvoxApiClient, entry, store) -> None:
        """Initialize the door log sensor."""
        super().__init__(client=client, entry=entry)
        self._store = store
        self._entries: list = []
        self._attr_unique_id = "Door Log"
        self._attr_name = "Door Log"
        self._attr_icon = "mdi:door"
        self._attr_should_poll = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "Door Log")},  # type: ignore
            name="Door Log",
            model=VERSION,
            manufacturer=NAME,
        )
        LOGGER.debug("Adding door log sensor")

    async def async_added_to_hass(self):
        """Subscribe to door log updates and load stored entries."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen("akuvox_door_log_updated", self._handle_door_log_updated))
        await self.async_reload_entries()

    async def _handle_door_log_updated(self, event):
        """Reload entries and update state when the poller detects a new log."""
        await self.async_reload_entries()
        self.async_write_ha_state()

    async def async_reload_entries(self):
        """Load the door log entries from integration storage."""
        stored_data: dict = await self._store.async_load() # type: ignore
        if stored_data:
            entries = stored_data.get("door_log_entries", [])
            self._entries = [entry for entry in entries if isinstance(entry, dict)]
        else:
            self._entries = []

    @property
    def native_value(self):
        """Return a readable summary of the newest door log entry."""
        latest = self._entries[0] if self._entries else None
        if latest:
            location = latest.get("location") or "?"
            initiator = latest.get("initiator") or "?"
            return f"{location} - {initiator}"
        return "No entries"

    @property
    def entity_picture(self):
        """Show the newest door log screenshot as the entity picture."""
        if self._entries:
            return self._entries[0].get("local_pic_url") or self._entries[0].get("pic_url")
        return None

    @property
    def extra_state_attributes(self):
        """Return the door log entries and latest entry as attributes."""
        latest = self._entries[0] if self._entries else None
        return {
            "entries": self._entries,
            "latest": latest,
            "count": len(self._entries),
        }
