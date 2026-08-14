"""Akuvox Data Class."""
from __future__ import annotations
# from dataclasses import dataclass

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import storage

from .const import (
    LOGGER,
    TEMP_KEY_QR_HOST,
    PIC_URL_KEY,
    CAPTURE_TIME_KEY,
    DATA_STORAGE_KEY,
    LOCATIONS_DICT,
)
from .helpers import AkuvoxHelpers

helpers = AkuvoxHelpers()

# @dataclass
class AkuvoxData:
    """Data class holding key data from API requests."""

    hass: HomeAssistant = None # type: ignore
    host: str = ""
    location_dict: dict = {}
    subdomain: str = ""
    app_type: str = ""
    auth_token: str = ""
    token: str = ""
    phone_number: str = ""
    wait_for_image_url: bool = False
    rtsp_ip: str = ""
    project_name: str = ""
    camera_data = []
    door_relay_data = []
    door_keys_data = []


    def __init__(self,
                 entry: ConfigEntry,
                 hass: HomeAssistant,
                 host: str = None, # type: ignore
                 subdomain: str = None, # type: ignore
                 auth_token: str = None, # type: ignore
                 token: str = None, # type: ignore
                 country_code: str = None, # type: ignore
                 phone_number: str = None, # type: ignore
                 wait_for_image_url: bool = False):
        """Initialize the Akuvox API client."""

        self.hass = hass if hass else self.hass
        self.host = host if host else self.get_value_for_key(entry, "host", host) # type: ignore
        self.token = token if token else self.get_value_for_key(entry, "token", self.token) # type: ignore
        self.auth_token = auth_token if auth_token else self.get_value_for_key(entry, "auth_token", self.token) # type: ignore
        self.phone_number = phone_number if phone_number else self.get_value_for_key(entry, "phone_number", self.phone_number) # type: ignore
        self.wait_for_image_url = wait_for_image_url if wait_for_image_url is not None else bool(self.get_value_for_key(entry, "event_screenshot_options", False) == "wait") # type: ignore

        self.subdomain = subdomain if subdomain else "scloud"

        self.hass.add_job(self.async_set_stored_data_for_key, "wait_for_image_url", self.wait_for_image_url)

    def get_value_for_key(self, entry: ConfigEntry, key: str, default):
        """Get the value for a given key. 1st check: configured, 2nd check: options, 3rd check: data."""
        if entry is not None:
            if isinstance(entry, dict):
                if key in entry["configured"]: # type: ignore
                    return entry["configured"][key] # type: ignore
                return default
            if key in entry.options:
                return entry.options[key]
            return entry.data.get(key, default)
        return default

    def parse_rest_server_response(self, json_data: dict):
        """Parse the rest_server API response."""
        if json_data is not None and json_data != {}:
            self.host = json_data["rest_server_https"]
            return True
        return self.host is None or len(self.host) == 0

    def parse_sms_login_response(self, json_data: dict):
        """Parse the sms_login API response."""
        if json_data is not None:
            if "auth_token" in json_data:
                self.auth_token = json_data["auth_token"]
            if "token" in json_data:
                self.token = json_data["token"]
            if not self.auth_token:
                self.auth_token = self.token
            if not self.token:
                self.token = self.auth_token
            if "rtmp_server" in json_data:
                self.rtsp_ip = json_data["rtmp_server"].split(':')[0]

    def parse_userconf_data(self, json_data: dict):
        """Parse the userconf API response."""
        self.door_relay_data = []
        self.camera_data = []
        if json_data is not None:
            if "app_conf" in json_data:
                self.project_name = json_data["app_conf"]["project_name"].strip()
            if "dev_list" in json_data:
                for dev_data in json_data["dev_list"]:
                    name = dev_data["location"].strip()
                    mac = dev_data["mac"]

                    # Camera
                    if "location" in dev_data and "rtsp_pwd" in dev_data and "mac" in dev_data:
                        password = dev_data["rtsp_pwd"]
                        camera_dict = {
                            "name": name,
                            "video_url": f"rtsp://ak:{password}@{self.rtsp_ip}:554/{mac}"
                        }
                        self.camera_data.append(camera_dict)

                    # Door Relay
                    if "relay" in dev_data and len(dev_data["relay"]) > 0:
                        for relay in dev_data["relay"]:
                            relay_id = relay["relay_id"]
                            door_name = relay["door_name"].strip()
                            self.door_relay_data.append({
                                "name": name,
                                "door_name": door_name,
                                "relay_id": relay_id,
                                "mac": mac
                            })
                    else:
                        self.door_relay_data.append({
                            "name": name,
                            "door_name": "Open",
                            "relay_id": "0",
                            "mac": mac
                        })

        # Log parsed entities
        if len(self.camera_data) > 0:
            LOGGER.debug("🎥 Cameras parsed:")
            for camera_dict in self.camera_data:
                LOGGER.debug(" - %s", camera_dict.get("name", ""))
        if len(self.door_relay_data) > 0:
            LOGGER.debug("🚪 Door relays parsed:")
            for relay_dict in self.door_relay_data:
                LOGGER.debug(" - %s", relay_dict.get("name", ""))

    def parse_temp_keys_data(self, json_data: list):
        """Parse the getPersonalTempKeyList API response."""
        self.door_keys_data = []
        for door_keys_json in json_data:
            door_keys_data = {}
            door_keys_data["key_id"] = door_keys_json["ID"]
            door_keys_data["description"] = door_keys_json["Description"]
            door_keys_data["key_code"] = door_keys_json["TmpKey"]
            door_keys_data["begin_time"] = door_keys_json["BeginTime"]
            door_keys_data["end_time"] = door_keys_json["EndTime"]
            door_keys_data["access_times"] = door_keys_json["AccessTimes"]
            door_keys_data["allowed_times"] = door_keys_json["AllowedTimes"]
            door_keys_data["each_allowed_times"] = door_keys_json["EachAllowedTimes"]
            door_keys_data["qr_code_url"] = f"https://{TEMP_KEY_QR_HOST}{door_keys_json['QrCodeUrl']}"
            door_keys_data["expired"] = False if door_keys_json["Expired"] else True

            door_keys_data["doors"] = []
            if "Doors" in door_keys_json:
                for door_key_json in door_keys_json["Doors"]:
                    door_keys_data["doors"].append({
                        "door_id": door_key_json["ID"],
                        "key_id": door_key_json["KeyID"],  # Reference to key
                        "relay": door_key_json["Relay"],
                        "mac": door_key_json["MAC"]
                    })

            self.door_keys_data.append(door_keys_data)

        if len(self.door_keys_data) > 0:
            LOGGER.debug("🔑 %s Temp key%s parsed:",
                        str(len(self.door_keys_data)),
                        "s" if len(self.door_keys_data) > 1 else "")
            for door_relay_dict in self.door_relay_data:
                LOGGER.debug(" - '%s', with access to %s door%s",
                             door_relay_dict.get("name", ""),
                             str(len(door_keys_data["doors"])),
                             "" if len(door_keys_data["doors"]) == 1 else "s")

    async def async_parse_personal_door_log(self, json_data: list):
        """Parse the getDoorLog API response."""
        ret_value = None
        is_wait = await self.async_get_stored_data_for_key("wait_for_image_url")
        if json_data is not None and isinstance(json_data, list) and len(json_data) > 0:
            new_door_log = json_data[0]
            latest_door_log = await self.async_get_stored_data_for_key("latest_door_log")
            if latest_door_log is not None and CAPTURE_TIME_KEY in latest_door_log:
                if new_door_log is not None and CAPTURE_TIME_KEY in new_door_log:
                    # Ignore previous door open event (same door at same time)
                    if (str(latest_door_log[CAPTURE_TIME_KEY]) == str(new_door_log[CAPTURE_TIME_KEY]) and
                            str(latest_door_log.get("MAC", "")) == str(new_door_log.get("MAC", "")) and
                            str(latest_door_log.get("Location", "")) == str(new_door_log.get("Location", ""))):
                        return None
                    # Screenshot required and currently unavailable
                    if PIC_URL_KEY in new_door_log and new_door_log[PIC_URL_KEY] == "":
                        if is_wait is True:
                            LOGGER.debug("New door entry detected --> Waiting for screenshot URL...")
                            return None
                        else:
                            LOGGER.debug("New door entry detected --> Not waiting for the screenshot URL...")
                    # New door event detected
                    LOGGER.debug("ℹ️ New personal door log entry detected:")
                    LOGGER.debug(" - Initiator: %s", new_door_log["Initiator"])
                    LOGGER.debug(" - CaptureType: %s", new_door_log["CaptureType"])
                    LOGGER.debug(" - Location: %s", new_door_log["Location"])
                    LOGGER.debug(" - Door MAC: %s", new_door_log["MAC"])
                    LOGGER.debug(" - Door Relay: %s", new_door_log["Relay"])
                    LOGGER.debug(" - Camera screenshot URL: %s", new_door_log["PicUrl"])
                    ret_value = new_door_log

            await self.async_set_stored_data_for_key("latest_door_log", new_door_log)
        return ret_value

    async def async_merge_door_log_entries(self, json_data: list):
        """Merge door log entries from API response into the stored list.

        Returns (changed, entries) where entries is newest-first and capped at 500.
        """
        entries = await self.async_get_stored_data_for_key("door_log_entries")
        if entries is None:
            entries = []
        entries = [entry for entry in entries if isinstance(entry, dict)]
        existing_keys = {
            f"{entry.get('capture_time')}|{entry.get('mac')}|{entry.get('location')}"
            for entry in entries
        }
        changed = False
        new_items = []
        for door_log_json in json_data:
            if not isinstance(door_log_json, dict):
                continue
            capture_time = door_log_json.get(CAPTURE_TIME_KEY, "")
            if not capture_time:
                continue
            key = f"{capture_time}|{door_log_json.get('MAC', '')}|{door_log_json.get('Location', '')}"
            if key in existing_keys:
                for entry in entries:
                    if entry.get("capture_time") == capture_time:
                        if not entry.get("capture_type") and door_log_json.get("CaptureType", ""):
                            entry["capture_type"] = door_log_json.get("CaptureType", "")
                            changed = True
                        if not entry.get("pic_url") and door_log_json.get(PIC_URL_KEY, ""):
                            entry["pic_url"] = door_log_json.get(PIC_URL_KEY, "")
                            entry["ss_attempts"] = 0
                            changed = True
                continue
            new_items.append({
                "capture_time": capture_time,
                "location": door_log_json.get("Location", ""),
                "initiator": door_log_json.get("Initiator", ""),
                "capture_type": door_log_json.get("CaptureType", ""),
                "relay": door_log_json.get("Relay", ""),
                "mac": door_log_json.get("MAC", ""),
                "building_name": door_log_json.get("BuildingName", ""),
                "room_num": door_log_json.get("RoomNum", ""),
                "pic_url": door_log_json.get(PIC_URL_KEY, ""),
                "local_pic_url": "",
                "ss_attempts": 0,
            })
            existing_keys.add(key)
            changed = True
        if changed:
            entries = new_items + entries
            entries.sort(key=lambda e: str(e.get("capture_time", "")), reverse=True)
            del entries[1000:]
            await self.async_set_stored_data_for_key("door_log_entries", entries)
        return changed, entries

    async def async_merge_call_log_entries(self, json_data: list):
        """Merge call history entries into the stored door log list.

        Returns (changed, entries) where entries is newest-first and capped at 1000.
        """
        entries = await self.async_get_stored_data_for_key("door_log_entries")
        if entries is None:
            entries = []
        entries = [entry for entry in entries if isinstance(entry, dict)]
        existing_keys = {
            f"{entry.get('capture_time')}|{entry.get('mac')}|{entry.get('location')}|{entry.get('entry_type', 'door')}|{entry.get('receiver', '')}"
            for entry in entries
        }
        changed = False
        new_items = []
        for call_json in json_data:
            if not isinstance(call_json, dict):
                continue
            capture_time = call_json.get("capture_time", "")
            if not capture_time:
                continue
            location = call_json.get("location", "")
            receiver = call_json.get("receiver", "")
            key = f"{capture_time}||{location}|call|{receiver}"
            if key in existing_keys:
                for entry in entries:
                    if (entry.get("capture_time") == capture_time and
                            entry.get("entry_type") == "call"):
                        if not entry.get("pic_url") and call_json.get("pic_url", ""):
                            entry["pic_url"] = call_json.get("pic_url", "")
                            entry["ss_attempts"] = 0
                            changed = True
                continue
            new_items.append({
                "capture_time": capture_time,
                "location": location,
                "initiator": call_json.get("initiator", ""),
                "receiver": receiver,
                "capture_type": "",
                "relay": "",
                "mac": "",
                "building_name": "",
                "room_num": "",
                "pic_url": call_json.get("pic_url", ""),
                "local_pic_url": "",
                "ss_attempts": 0,
                "entry_type": "call",
                "is_answer": bool(call_json.get("is_answer", False)),
                "is_callee": bool(call_json.get("is_callee", False)),
                "is_read": bool(call_json.get("is_read", False)),
                "is_group_call": bool(call_json.get("is_group_call", False)),
            })
            existing_keys.add(key)
            changed = True
        if changed:
            entries = new_items + entries
            entries.sort(key=lambda e: str(e.get("capture_time", "")), reverse=True)
            del entries[1000:]
            await self.async_set_stored_data_for_key("door_log_entries", entries)
        return changed, entries

    ###################

    async def async_set_stored_data_for_key(self, key, value):
        """Store key/value pair to integration's storage."""
        store = storage.Store(self.hass, 1, DATA_STORAGE_KEY)
        stored_data: dict = await store.async_load() # type: ignore
        if stored_data is None:
            stored_data = {}
        stored_data[key] = value
        await store.async_save(stored_data)

    async def async_get_stored_data_for_key(self, key):
        """Store key/value pair to integration's storage."""
        store = storage.Store(self.hass, 1, DATA_STORAGE_KEY)
        stored_data: dict = await store.async_load() # type: ignore
        if stored_data:
            return stored_data.get(key, None)

    ###################

    def get_device_data(self) -> dict:
        """Device data dictionary."""
        return {
            "host": self.host,
            "token": self.token,
            "auth_token": self.auth_token,
            "camera_data": self.camera_data,
            "door_relay_data": self.door_relay_data,
            "door_keys_data": self.door_keys_data
        }
