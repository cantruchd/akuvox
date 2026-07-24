"""Button platform for akuvox."""
import asyncio

from homeassistant.components.button import ButtonEntity
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
    """Set up the door relay platform."""
    coordinator: AkuvoxDataUpdateCoordinator
    for _key, value in hass.data[DOMAIN].items():
        coordinator = value
    client = coordinator.client

    store = storage.Store(hass, 1, DATA_STORAGE_KEY)
    device_data: dict = await store.async_load() # type: ignore
    if not device_data or "door_relay_data" not in device_data:
        LOGGER.error("No door relay data found")
        return
    door_relay_data = device_data["door_relay_data"]

    entities = []
    all_doors_data = []

    for door_relay in door_relay_data:
        name = door_relay["name"]
        mac = door_relay["mac"]
        relay_id = door_relay["relay_id"]
        data = f"mac={mac}&relay={relay_id}"

        entities.append(
            AkuvoxDoorRelayEntity(
                client=client,
                entry=entry,
                name=name,
                relay_id=relay_id,
                data=data,
            )
        )
        all_doors_data.append((name, data))

    entities.append(
        AkuvoxOpenAllEntity(
            client=client,
            entry=entry,
            doors_data=all_doors_data,
        )
    )

    async_add_devices(entities)


class AkuvoxDoorRelayEntity(ButtonEntity, AkuvoxEntity):
    """Akuvox door relay class."""

    _client: AkuvoxApiClient
    _name: str = ""
    _host: str = ""
    _token: str = ""
    _data: str = ""

    def __init__(
        self,
        client: AkuvoxApiClient,
        entry,
        name: str,
        relay_id: str,
        data: str,
    ) -> None:
        """Initialize the Akuvox door relay class."""
        super(ButtonEntity, self).__init__(client=client, entry=entry)
        AkuvoxEntity.__init__(
            self=self,
            client=client,
            entry=entry
        )
        unique_name = name + ", " + relay_id
        self._client = client
        self._name = unique_name
        self._host = self.get_saved_value("host")
        self._token = self.get_saved_value("token")
        self._data = data

        self._attr_unique_id = unique_name
        self._attr_name = unique_name

        LOGGER.debug("Adding Akuvox door relay '%s'", unique_name)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, name)},  # type: ignore
            name=name,
            model=VERSION,
            manufacturer=NAME,
        )

    async def async_press(self) -> None:
        """Trigger the door relay."""
        await self._client.async_make_opendoor_request(
            name=self._name,
            host=self._host,
            token=self._token,
            data=self._data
        )


class AkuvoxOpenAllEntity(ButtonEntity, AkuvoxEntity):
    """Button to open all doors concurrently."""

    _client: AkuvoxApiClient
    _doors_data: list = []

    def __init__(
        self,
        client: AkuvoxApiClient,
        entry,
        doors_data: list,
    ) -> None:
        """Initialize."""
        super(ButtonEntity, self).__init__(client=client, entry=entry)
        AkuvoxEntity.__init__(self=self, client=client, entry=entry)
        self._client = client
        self._host = self.get_saved_value("host")
        self._token = self.get_saved_value("token")
        self._doors_data = doors_data

        self._attr_unique_id = "open_all_doors"
        self._attr_name = "Open All Doors"

        LOGGER.debug("Adding Akuvox open all doors button")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "open_all_doors")},  # type: ignore
            name="All Doors",
            model=VERSION,
            manufacturer=NAME,
        )

    async def async_press(self) -> None:
        """Open all doors concurrently."""
        tasks = [
            self._client.async_make_opendoor_request(
                name=name,
                host=self._host,
                token=self._token,
                data=data,
            )
            for name, data in self._doors_data
        ]
        await asyncio.gather(*tasks)

