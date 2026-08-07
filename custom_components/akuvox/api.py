"""Akuvox API Client."""
from __future__ import annotations

import asyncio
import socket
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from homeassistant.core import HomeAssistant

import aiohttp
import async_timeout
import requests

from .data import AkuvoxData
from .door_poll import DoorLogPoller

from .const import (
    LOGGER,
    REST_SERVER_ADDR,
    REST_SERVER_PORT,
    API_SEND_SMS,
    SMS_LOGIN_API_VERSION,
    API_SMS_LOGIN,
    API_SERVERS_LIST,
    REST_SERVER_API_VERSION,
    API_REST_SERVER_DATA,
    USERCONF_API_VERSION,
    API_USERCONF,
    OPENDOOR_API_VERSION,
    API_OPENDOOR,
    API_APP_HOST,
    API_GET_PERSONAL_TEMP_KEY_LIST,
    API_GET_PERSONAL_DOOR_LOG,
    API_V4_HOST,
    API_V4_GET_PERSONAL_DOOR_LOG,
    CAPTURE_TIME_KEY,
    PIC_URL_KEY
)


class AkuvoxApiClientError(Exception):
    """Exception to indicate a general API error."""


class AkuvoxApiClientCommunicationError(AkuvoxApiClientError):
    """Exception to indicate a communication error."""


class AkuvoxApiClientAuthenticationError(AkuvoxApiClientError):
    """Exception to indicate an authentication error."""

class AkuvoxApiClient:
    """Sample API Client."""

    _data: AkuvoxData = None # type: ignore
    hass: HomeAssistant
    door_log_poller: DoorLogPoller
    _last_error: dict | None = None

    def __init__(
        self,
        session: aiohttp.ClientSession,
        hass: HomeAssistant,
        entry,
    ) -> None:
        """Akuvox API Client."""
        self._session = session
        self.hass = hass
        self._last_error = None
        if entry:
            LOGGER.debug("▶️ Initializing AkuvoxData from API client init")
            self._data = AkuvoxData(
                entry=entry,
                hass=hass) # type: ignore

    async def async_init_api(self) -> bool:
        """Initialize API configuration data."""
        self._data.host = "...request in process"
        if await self.async_fetch_rest_server() is False:
            return False

        if self._data.host is None or len(self._data.host) == 0:
            LOGGER.error("❌ Unable to find API host address.")
            return False

        await self.async_fetch_vrtsp_server()

        return True

    async def async_start_polling(self):
        """Start polling the personal door log API."""
        self.door_log_poller: DoorLogPoller = DoorLogPoller(
            hass=self.hass,
            poll_function=self.async_retrieve_personal_door_log)
        await self.door_log_poller.async_start()

    async def async_stop_polling(self):
        """Stop polling the personal door log API."""
        await self.door_log_poller.async_stop()

    def init_api_with_data(self,
                           hass: HomeAssistant,
                           host=None,
                           subdomain=None,
                           auth_token=None,
                           token=None,
                           phone_number=None,
                           country_code=None):
        """"Initialize values from saved data/options."""
        if not self._data:
            LOGGER.debug("▶️ Initializing AkuvoxData from API client init_api_with_data")
            self._data = AkuvoxData(
                entry=None, # type: ignore
                hass=hass,
                host=host, # type: ignore
                subdomain=subdomain, # type: ignore
                auth_token=auth_token, # type: ignore
                token=token, # type: ignore
                phone_number=phone_number, # type: ignore
                country_code=country_code) # type: ignore
        self.hass = self.hass if self.hass else hass

    ####################
    # API Call Methods #
    ####################

    def _log_api(self, fn: str, token: str, url: str):
        LOGGER.debug("[API] %s | token=%s | url=%s", fn, token, url)

    async def async_fetch_rest_server(self):
        """Retrieve the Akuvox REST server addresses and data."""
        LOGGER.debug("📡 Fetching REST server data...")
        url = f"https://{REST_SERVER_ADDR}:{REST_SERVER_PORT}/{API_REST_SERVER_DATA}"
        self._log_api("async_fetch_rest_server", "", url)
        json_data = await self._async_api_wrapper(
            method="get",
            url=url,
            data=None,
            headers={
                'api-version': REST_SERVER_API_VERSION
            }
        )
        if json_data is not None:
            LOGGER.debug("✅ REST server data received successfully")
            if self._data.parse_rest_server_response(json_data): # type: ignore
                return True
            LOGGER.error("❌ Unable to parse Akuvox server rest API data.")
        else:
            LOGGER.error("❌ Unable to fetch Akuvox server rest API data.")
        return False

    async def async_fetch_vrtsp_server(self):
        """Fetch vrtsp_server from servers_list (GET) for RTSP stream IP."""
        if not self._data.token:
            return
        LOGGER.debug("📡 Fetching VRTSP server data...")
        url = f"https://{REST_SERVER_ADDR}:{REST_SERVER_PORT}/{API_SERVERS_LIST}?token={self._data.token}"
        self._log_api("async_fetch_vrtsp_server", self._data.token, url)
        json_data = await self._async_api_wrapper(
            method="get",
            url=url.replace("subdomain.", f"{self._data.subdomain}."),
            data=None,
            headers={}
        )
        if json_data is not None and "vrtsp_server" in json_data:
            ip = json_data["vrtsp_server"].split(':')[0]
            self._data.rtsp_ip = ip
            LOGGER.debug("✅ VRTSP server IP: %s", ip)

    async def async_send_sms(self, hass:HomeAssistant, country_code, phone_number, subdomain):
        """Request SMS code to user's device."""
        self.init_api_with_data(
            hass=hass,
            subdomain=subdomain,
            country_code=country_code,
            phone_number=phone_number)
        if await self.async_init_api():
            url = f"https://{self._data.host}/{API_SEND_SMS}".replace(".subdomain", f".{subdomain}")
            LOGGER.debug("url = %s", url)
            headers = {
                "Host": self._data.host,
                "Content-Type": "application/x-www-form-urlencoded",
                "X-AUTH-TOKEN": "",
                "Connection": "keep-alive",
                "Accept": "*/*",
                "User-Agent": "VBell/6.61.2 (iPhone; iOS 16.6; Scale/3.00)",
                "Accept-Language": "en-AU;q=1, he-AU;q=0.9, ru-RU;q=0.8",
                "x-cloud-lang": "en"
            }
            data = {
                "AreaCode": country_code,
                "MobileNumber": phone_number,
                "Type": 0
            }
            LOGGER.debug("📡 Requesting SMS code from subdomain %s...", subdomain)
            response = await self._async_api_wrapper(
                method="post",
                url=url,
                headers=headers,
                data=data,
            )
            if response is not None:
                if response["result"] == 0: # type: ignore
                    LOGGER.debug("✅ SMS code request successful")
                    return True

            LOGGER.error("❌ SMS code request unsuccessful. Request URL: %s", url)
        else:
            LOGGER.error("❌ Unable to initialize API. Did you login again from your device? Try logging in/adding tokens again.")
        return False

    async def async_make_servers_list_request(self,
                                               hass: HomeAssistant,
                                               auth_token: str,
                                               token: str,
                                               country_code,
                                               phone_number: str,
                                               subdomain: str = "") -> bool:
        """Request server list data."""
        if not auth_token:
            auth_token = token
        self._log_api("async_make_servers_list_request", token, f"gate.{subdomain}.akuvox.com:8600/servers_list")
        self.init_api_with_data(
            hass=hass,
            subdomain=subdomain,
            auth_token=auth_token,
            token=token,
            country_code=country_code,
            phone_number=phone_number)
        if await self.async_init_api() is False:
            return False


        # Build progressive request bodies (try removing passwd)
        obfuscated_number = str(self.get_obfuscated_phone_number(phone_number))
        request_bodies = [
            {"auth_token": auth_token, "token": token, "user": obfuscated_number},         # no passwd
            {"auth_token": auth_token, "passwd": auth_token, "token": token, "user": obfuscated_number},  # original
        ]

        # Try each body against the primary gate URL
        for body in request_bodies:
            data = json.dumps(body)
            headers = {
                "accept": "*/*",
                "content-type": "application/json",
                "x-auth-token": token,
                "api-version": "6.6",
                "x-cloud-lang": "en",
                "user-agent": "VBell/6.61.2 (iPhone; iOS 16.6; Scale/3.00)",
                "accept-language": "en-AU;q=1, he-AU;q=0.9, ru-RU;q=0.8"
            }
            url = f"https://{REST_SERVER_ADDR}:{REST_SERVER_PORT}/{API_SERVERS_LIST}"
            LOGGER.debug("📡 Requesting server list from %s...", url.replace("subdomain.", f"{self._data.subdomain}."))
            LOGGER.debug("Headers: x-auth-token=%s***, api-version=6.6, body=%s",
                         token[:5] if token and len(token) > 5 else "",
                         json.dumps({k: (v[:5]+"***" if k != "user" and len(v) > 5 else v) for k, v in body.items()}))
            json_data = await self._async_api_wrapper(
                method="post",
                url=url,
                headers=headers,
                data=data,
            )
            if json_data is not None:
                LOGGER.debug("✅ Server list retrieved successfully")
                self._data.parse_sms_login_response(json_data) # type: ignore
                return True

        LOGGER.error("❌ Unable to retrieve server list. Try signing in again / check that your tokens are valid.")
        if self._last_error and self._last_error.get("result") == -1:
            raise AkuvoxApiClientAuthenticationError(
                self._last_error.get("message", "Invalid or expired tokens"))
        return False

    async def async_sms_sign_in(self, phone_number, country_code, sms_code) -> bool:
        """Sign user in with their phone number and SMS code."""

        login_data = await self.async_validate_sms_code(phone_number, country_code, sms_code)
        if login_data is not None:
            self._data.parse_sms_login_response(login_data) # type: ignore

            # Retrieve connected device data
            await self.async_retrieve_device_data()
            await self.async_retrieve_temp_keys_data()

            return True

        return False

    async def async_validate_sms_code(self, phone_number, country_code, sms_code):
        """Validate the SMS code received by the user."""
        LOGGER.debug("📡 Logging in user with phone number and SMS code...")

        obfuscated_number = self.get_obfuscated_phone_number(phone_number)
        params = f"phone={obfuscated_number}&code={sms_code}&area_code={country_code}"
        url = f"https://{REST_SERVER_ADDR}:{REST_SERVER_PORT}/{API_SMS_LOGIN}?{params}"
        data = {}
        headers = {
            'api-version': SMS_LOGIN_API_VERSION,
            'User-Agent': 'VBell/6.61.2 (iPhone; iOS 16.6; Scale/3.00)'
        }
        response = await self._async_api_wrapper(method="get", url=url, headers=headers, data=data)

        if response is not None:
            LOGGER.debug("✅ Login successful")
            return response

        LOGGER.error("❌ Unable to log in with SMS code.")
        return None

    async def async_retrieve_user_data(self) -> bool:
        """Retrieve user devices and temp keys data."""
        self._log_api("async_retrieve_user_data", self._data.token, "")
        try:
            servers_ok = await self.async_make_servers_list_request(
                hass=self.hass,
                auth_token=self._data.auth_token,
                token=self._data.token,
                country_code=self.hass.config.country,
                phone_number=self._data.phone_number)
            if not servers_ok:
                LOGGER.warning("⚠️ Servers_list failed (skipping to device data fetch)")
        except AkuvoxApiClientAuthenticationError:
            LOGGER.warning("⚠️ Servers_list auth failed (skipping to device data fetch)")
        except Exception as e:
            LOGGER.warning("⚠️ Servers_list request error: %s (skipping)", e)

        await self.async_retrieve_device_data()
        await self.async_retrieve_temp_keys_data()
        return True

    async def async_retrieve_device_data(self) -> bool:
        """Request and parse the user's device data."""
        user_conf_data = await self.async_user_conf()
        if user_conf_data is not None:
            self._data.parse_userconf_data(user_conf_data) # type: ignore
            return True
        return False

    async def async_retrieve_user_data_with_tokens(self, auth_token, token) -> bool:
        """Retrieve user devices and temp keys data with an alternate token string."""
        self._log_api("async_retrieve_user_data_with_tokens", token, "")
        self._data.auth_token = auth_token or token
        self._data.token = token
        return await self.async_retrieve_user_data()

    async def async_user_conf(self):
        """Request the user's configuration data."""
        url = f"https://{self._data.host}/{API_USERCONF}?token={self._data.token}"
        self._log_api("async_user_conf", self._data.token, url)
        LOGGER.debug("📡 Retrieving list of user's devices...")
        data = {}
        headers = {
            "Host": self._data.host,
            "X-AUTH-TOKEN": self._data.token,
            "Connection": "keep-alive",
            "api-version": USERCONF_API_VERSION,
            "Accept": "*/*",
            "User-Agent": "VBell/6.61.2 (iPhone; iOS 16.6; Scale/3.00)",
            "Accept-Language": "en-AU;q=1, he-AU;q=0.9, ru-RU;q=0.8",
            "x-cloud-lang": "en"
        }
        json_data = await self._async_api_wrapper(method="post", url=url, headers=headers, data=data)

        if json_data is not None:
            LOGGER.debug("✅ User's device list retrieved successfully")
            return json_data

        LOGGER.error("❌ Unable to retrieve user's device list.")
        return None

    async def async_make_opendoor_request(self, name: str, host: str, token: str, data: str):
        """Request to open door via REST API."""
        # Force use rest server host for opendoor to avoid gate server issues
        rest_host = "rest.scloud.akuvox.com:8443"
        url = f"https://{rest_host}/{API_OPENDOOR}?token={token}"
        self._log_api("async_make_opendoor_request", token, url)
        LOGGER.warning("📡 Opening door '%s' via %s data=%s", name, url, data)
        headers = {
            "Host": rest_host,
            "Content-Type": "application/x-www-form-urlencoded",
            "X-AUTH-TOKEN": token,
            "api-version": OPENDOOR_API_VERSION,
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "*/*",
            "User-Agent": "VBell/6.61.2 (iPhone; iOS 16.6; Scale/3.00)",
            "Accept-Language": "en-AU;q=1, he-AU;q=0.9, ru-RU;q=0.8",
            "x-cloud-lang": "en",
        }
        try:
            response = await self.hass.async_add_executor_job(self.post_request, url, headers, data, 10)
            json_data = self.process_response(response, url)
            if json_data is not None:
                LOGGER.warning("✅ Door '%s' opened successfully", name)
                return json_data
            LOGGER.error("❌ Door '%s' failed (API returned error: %s)", name, response.text)
        except Exception as err:
            LOGGER.error("❌ Door '%s' request error: %s", name, err)
        return None

    async def async_retrieve_temp_keys_data(self) -> bool:
        """Request and parse the user's temporary keys."""
        json_data = await self.async_get_temp_key_list()
        if json_data is not None:
            self._data.parse_temp_keys_data(json_data)
            return True
        return False

    async def async_get_temp_key_list(self):
        """Request the user's configuration data."""
        host = self.get_activities_host()
        url = f"https://{host}/{API_GET_PERSONAL_TEMP_KEY_LIST}"
        self._log_api("async_get_temp_key_list", self._data.token, url)
        LOGGER.debug("📡 Retrieving list of user's temporary keys...")
        subdomain = self._data.subdomain
        url = f"https://{host}/{API_GET_PERSONAL_TEMP_KEY_LIST}"
        data = {}
        headers = {
            "x-cloud-version": "6.4",
            "accept": "application/json, text/plain, */*",
            "sec-fetch-site": "same-origin",
            "accept-language": "en-AU,en;q=0.9",
            "sec-fetch-mode": "cors",
            "x-cloud-lang": "en",
            "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) SmartPlus/6.2",
            "referer": f"https://{subdomain}.akuvox.com/smartplus/TmpKey.html?TOKEN={self._data.token}&USERTYPE=20&VERSION=6.6",
            "x-auth-token": self._data.token,
            "sec-fetch-dest": "empty"
        }

        json_data = await self._async_api_wrapper(method="get", url=url, headers=headers, data=data)

        if json_data is not None:
            LOGGER.debug("✅ User's temporary keys list retrieved successfully")
            return json_data

        LOGGER.error("❌ Unable to retrieve user's temporary key list.")
        return None

    async def async_start_polling_personal_door_log(self):
        """Poll the server contineously for the latest personal door log."""
        # Make sure only 1 instance of the door log polling is running
        self.hass.async_create_task(self.async_retrieve_personal_door_log())

    async def async_retrieve_personal_door_log(self) -> bool:
        """Request and parse the user's door log every 2 seconds."""
        while True:
            try:
                # Get the latest pesonal door log
                json_data = await self.async_get_personal_door_log()
                if json_data is not None:
                    # Update the door log entry list + download screenshots
                    await self.async_update_door_log_data(json_data)
                    # Fire HA event
                    new_door_log = await self._data.async_parse_personal_door_log(json_data)
                    if new_door_log is not None:
                        LOGGER.debug("🚪 New door open event occurred. Firing akuvox_door_update event")
                        event_name = "akuvox_door_update"
                        entries = await self._data.async_get_stored_data_for_key("door_log_entries")
                        if (entries and str(entries[0].get("capture_time")) ==
                                str(new_door_log.get(CAPTURE_TIME_KEY))):
                            if entries[0].get("local_pic_url"):
                                new_door_log["LocalPicUrl"] = entries[0]["local_pic_url"]
                        self.hass.bus.async_fire(event_name, new_door_log)
            except Exception as error:  # pylint: disable=broad-except
                LOGGER.error("❌ Door log polling error: %s", error)
            await asyncio.sleep(2)  # Wait for 2 seconds before calling again

    async def async_update_door_log_data(self, json_data):
        """Merge door log entries into the stored list and download screenshots.

        Notifies the door log sensor via the 'akuvox_door_log_updated' event.
        """
        try:
            if not isinstance(json_data, list):
                LOGGER.debug("⏭️ Door log response is not a list (%s), skipping merge",
                             type(json_data).__name__)
                return
            changed, entries = await self._data.async_merge_door_log_entries(json_data)
            needs_download = any(
                entry.get("local_pic_url") == "" and entry.get("pic_url")
                and entry.get("ss_attempts", 0) < 5
                for entry in entries)
            if not changed and not needs_download:
                return
            attempted = False
            for entry in entries:
                if entry.get("local_pic_url") or not entry.get("pic_url"):
                    continue
                if entry.get("ss_attempts", 0) >= 5:
                    continue
                attempted = True
                local_pic_url = await self.async_download_door_screenshot(
                    entry["pic_url"], entry["capture_time"])
                entry["ss_attempts"] = entry.get("ss_attempts", 0) + 1
                if local_pic_url:
                    entry["local_pic_url"] = local_pic_url
            if attempted:
                await self._data.async_set_stored_data_for_key("door_log_entries", entries)
            if changed or attempted:
                self.hass.bus.async_fire("akuvox_door_log_updated")
        except Exception as error:  # pylint: disable=broad-except
            LOGGER.error("❌ Error updating door log data: %s", error)

    async def async_download_door_screenshot(self, pic_url: str, capture_time: str) -> str | None:
        """Download door log screenshot to www/akuvox and return local URL.

        Screenshots older than 30 days are automatically deleted to avoid
        filling up the disk.
        """
        www_dir = Path(self.hass.config.path("www", "akuvox"))
        filename = self._get_screenshot_filename(capture_time, pic_url)
        local_path = www_dir / filename
        if local_path.exists():
            LOGGER.debug("✅ Door screenshot already exists: %s", filename)
            return f"/local/akuvox/{filename}"
        try:
            www_dir.mkdir(parents=True, exist_ok=True)
            headers = {
                "accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                "user-agent": "Mozilla/5.0 (Linux; Android 15; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/150.0.7871.181 Mobile Safari/537.36 SmartPlus/6.2",
                "x-auth-token": self._data.token,
                "referer": f"https://{self._data.subdomain}.akuvox.com/",
            }
            url = pic_url
            response = await self.hass.async_add_executor_job(self.get_request, url, headers, None, 20)
            if response.status_code in (401, 403):
                # Retry with token in the query string
                separator = "&" if "?" in pic_url else "?"
                url = f"{pic_url}{separator}token={self._data.token}"
                response = await self.hass.async_add_executor_job(self.get_request, url, headers, None, 20)
            if response.status_code == 200 and response.content:
                await self.hass.async_add_executor_job(
                    self._save_screenshot_and_cleanup, local_path, response.content)
                LOGGER.info("🖼️ Door screenshot saved to %s", local_path)
                return f"/local/akuvox/{filename}"
            LOGGER.warning("❌ Unable to download door screenshot (HTTP %s): %s",
                           response.status_code, url)
        except Exception as error:  # pylint: disable=broad-except
            LOGGER.error("❌ Error downloading door screenshot: %s", error)
        return None

    def _get_screenshot_filename(self, capture_time: str, pic_url: str) -> str:
        """Build a safe filename from capture time and source URL extension."""
        safe_time = re.sub(r"\D", "", str(capture_time))
        extension = Path(urlparse(pic_url).path).suffix.lower()
        if extension not in (".jpg", ".jpeg", ".png", ".webp"):
            extension = ".jpg"
        return f"door_{safe_time}{extension}"

    def _save_screenshot_and_cleanup(self, local_path: Path, content: bytes):
        """Write screenshot to disk and remove screenshots older than 30 days."""
        try:
            local_path.write_bytes(content)
        except OSError as error:
            LOGGER.error("❌ Unable to save door screenshot %s: %s", local_path, error)
            return
        self.cleanup_old_screenshots(local_path.parent)

    def cleanup_old_screenshots(self, www_dir: Path):
        """Delete door screenshots older than 30 days."""
        cutoff = time.time() - (30 * 24 * 60 * 60)
        removed = 0
        try:
            for file_path in www_dir.iterdir():
                if not file_path.is_file():
                    continue
                try:
                    if file_path.stat().st_mtime < cutoff:
                        file_path.unlink()
                        removed += 1
                except OSError:
                    continue
        except OSError as error:
            LOGGER.warning("🧹 Unable to scan %s for old screenshots: %s", www_dir, error)
        if removed:
            LOGGER.info("🧹 Deleted %s door screenshot(s) older than 30 days", removed)

    async def async_get_personal_door_log(self):
        """Request the user's personal door log data."""
        import time
        app_type = self._data.app_type or "single"
        ts = int(time.time() * 1000)
        path = API_V4_GET_PERSONAL_DOOR_LOG.replace("single/", f"{app_type}/")
        url = f"https://{API_V4_HOST}{path}&_t={ts}"
        self._log_api("async_get_personal_door_log", self._data.token, url)
        data = {}
        subdomain = self._data.subdomain
        headers = {
            "x-cloud-version": "6.4",
            "accept": "application/json, text/plain, */*",
            "sec-fetch-site": "same-site",
            "accept-language": "en-GB,en;q=0.9",
            "sec-fetch-mode": "cors",
            "x-cloud-lang": "en",
            "origin": f"https://{subdomain}.akuvox.com",
            "x-requested-with": "com.akuvox.mobile.smartplus",
            "pragma": "no-cache",
            "cache-control": "no-cache",
            "user-agent": f"Mozilla/5.0 (Linux; Android 15; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/150.0.7871.181 Mobile Safari/537.36 SmartPlus/6.2",
            "referer": f"https://{subdomain}.akuvox.com/",
            "x-auth-token": self._data.token,
            "sec-fetch-dest": "empty"
        }

        json_data: list = await self._async_api_wrapper(method="get",
                                                        url=url,
                                                        headers=headers,
                                                        data=data)

        if json_data is not None and len(json_data) > 0:
            return json_data

        LOGGER.debug("No door log entries found")
        return None

    ###################
    # Request Methods #
    ###################

    async def _async_api_wrapper(
        self,
        method: str,
        url: str,
        data,
        headers: dict | None = None,
    ):
        """Get information from the API."""
        try:
            async with async_timeout.timeout(10):
                func = self.post_request if method == "post" else self.get_request
                subdomain = self._data.subdomain
                url = url.replace("subdomain.", f"{subdomain}.")
                if not url.endswith(API_GET_PERSONAL_DOOR_LOG):
                    LOGGER.debug("⏳ Sending request to %s", url)
                response = await self.hass.async_add_executor_job(func, url, headers, data, 10)
                return self.process_response(response, url)

        except asyncio.TimeoutError as exception:
            # Fix for accounts which use the "single" endpoint instead of "community"
            app_type_1 = "community"
            app_type_2 = "single"
            for prefix in [f"app/{app_type_1}/", f"{app_type_1}/"]:
                if prefix in url:
                    LOGGER.warning("Request '%s' API %s request timed out: %s - Retry using '%s'",
                                   app_type_1, method, url, app_type_2)
                    self._data.app_type = app_type_2
                    url = url.replace(prefix, f"{app_type_2}/")
                    return await self._async_api_wrapper(method, url, data, headers)
            for prefix in [f"app/{app_type_2}/", f"{app_type_2}/"]:
                if prefix in url:
                    LOGGER.error("Timeout occured for 'app/%s' API %s request: %s",
                                 app_type_2, method, url)
                    self._data.app_type = app_type_1
            raise AkuvoxApiClientCommunicationError(
                f"Timeout error fetching information: {exception}",
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            raise AkuvoxApiClientCommunicationError(
                f"Error fetching information: {exception}",
            ) from exception
        except Exception as exception:  # pylint: disable=broad-except
            raise AkuvoxApiClientError(
                f"Something really wrong happened! {exception}. URL = {url}"
            ) from exception
        return None

    def process_response(self, response, url):
        """Process response and return dict with data."""
        self._last_error = None
        if response.status_code == 200:
            # Assuming the response is valid JSON, parse it
            try:
                json_data = response.json()

                # Door log requests: raw list response
                if isinstance(json_data, list):
                    return json_data

                # Standard requests
                if "result" in json_data:
                    if json_data["result"] == 0:
                        if "datas" in json_data:
                            return json_data["datas"]
                        if "data" in json_data:
                            return json_data["data"]
                        return json_data
                    self._last_error = json_data
                    LOGGER.warning("🤨 Response: %s", str(json_data))
                    return None

                # Temp key requests
                if "code" in json_data:
                    if json_data["code"] == 0:
                        if "data" in json_data:
                            return json_data["data"]
                        return json_data
                    return []

                LOGGER.warning("🤨 Response: %s", str(json_data))
            except Exception as error:
                LOGGER.error("❌ Error occurred when parsing JSON: %s\nRequest: %s",
                             error,
                             url)
        else:
            LOGGER.debug("❌ Error: HTTP status code = %s for request to %s",
                         response.status_code,
                         url)
        return None

    async def async_make_get_request(self, url, headers, data=None):
        """Make an HTTP get request."""
        return await self.async_make_request("get", url, headers, data)

    async def async_make_post_request(self, url, headers, data=None):
        """Make an HTTP post request."""
        return await self.async_make_request("post", url, headers, data)

    async def async_make_request(self, request_type, url, headers, data=None):
        """Make an HTTP request."""
        func = self._session.post if request_type == "post" else self._session.get

        response = await func(url=url, headers=headers, data=data)
        if response is not None:
            if response.status == 200:
                # Assuming the response is valid JSON, parse it
                try:
                    json_data = await response.json()
                    return json_data
                except Exception as error:
                    LOGGER.warning(
                        "❌ Error occurred when parsing JSON: %s", error)
            else:
                LOGGER.debug("❌ Error: HTTP status code %s",
                             response.status)
                return None

    def post_request(self, url, headers, data="", timeout=10):
        """Make a synchronous post request."""
        response: requests.Response = requests.post(url,
                                                    headers=headers,
                                                    data=data,
                                                    timeout=timeout)
        return response

    def get_request(self, url, headers, data, timeout=10):
        """Make a synchronous post request."""
        response: requests.Response = requests.get(url,
                                                   headers=headers,
                                                   data=data,
                                                   timeout=timeout)
        return response

    ###########
    # Getters #
    ###########

    def get_title(self) -> str:
        """Title of Akuvox account."""
        return self._data.project_name

    def get_devices_json(self) -> dict:
        """Device data dictionary."""
        return self._data.get_device_data()

    def get_obfuscated_phone_number(self, phone_number):
        """Obfuscate the user's phone number for API requests."""
        if (phone_number is None or len(phone_number) == 0):
            LOGGER.error("No phone number provided for obfuscation")
        # Mask phone number
        try:
            num_str = re.sub(r'\D', '', str(phone_number))
        except Exception as error:
            LOGGER.error("Unable to get obfuscated phone number from %s: %s",
                         str(phone_number),
                         str(error))
            return False
        transformed_str = ""
        # Iterate through each digit in the input number
        for digit_char in num_str:
            digit = int(digit_char)
            # Add 3 to the digit and take the result modulo 10
            transformed_digit = (digit + 3) % 10
            transformed_str += str(transformed_digit)
        return int(transformed_str)

    def get_activities_host(self):
        """Get the host address string for activities API requests."""
        if self._data.app_type == "single":
            return API_APP_HOST + "single"
        return API_APP_HOST + "community"

    def switch_activities_host(self):
        """Switch the activities host from single <--> community."""
        if self._data.app_type == "single":
            LOGGER.debug("Switching API address from 'single' to 'community'")
            self._data.app_type = "community"
        else:
            self._data.app_type = "single"
            LOGGER.debug("Switching API address from 'community' to 'single'")

    def update_data(self, key, value):
        """Update the data model."""
        self._data.subdomain = value if key == "subdomain" else self._data.subdomain
        self._data.auth_token = value if key == "auth_token" else self._data.auth_token
        self._data.token = value if key == "token" else self._data.token
        self._data.wait_for_image_url = value if key == "wait_for_image_url" else self._data.wait_for_image_url
