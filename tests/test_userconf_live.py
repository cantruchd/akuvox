"""Live integration test for async_user_conf.
Requires env vars: AKUVOX_AUTH_TOKEN, AKUVOX_TOKEN, AKUVOX_PHONE, AKUVOX_SUBDOMAIN

Usage:
  $env:AKUVOX_AUTH_TOKEN="..."; $env:AKUVOX_TOKEN="..."; $env:AKUVOX_PHONE="..."; python -m pytest tests/test_userconf_live.py -v -s
"""
import os
import json
import urllib.request
import urllib.error
import pytest

REST_SERVER = "https://gate.scloud.akuvox.com:8600"


def obfuscate(num):
    return "".join(str((int(d) + 3) % 10) for d in str(num))


def _get_creds():
    auth_token = os.environ.get("AKUVOX_AUTH_TOKEN")
    token = os.environ.get("AKUVOX_TOKEN")
    phone = os.environ.get("AKUVOX_PHONE")
    subdomain = os.environ.get("AKUVOX_SUBDOMAIN", "scloud")
    if not all([auth_token, token, phone]):
        return None
    return auth_token, token, phone, subdomain


def test_get_host():
    """Step 1: Call rest_server API to get the host."""
    creds = _get_creds()
    if not creds:
        pytest.skip("Set AKUVOX_AUTH_TOKEN, AKUVOX_TOKEN, AKUVOX_PHONE env vars")
    auth_token, token, phone, subdomain = creds

    url = f"https://gate.{subdomain}.akuvox.com:8600/rest_server"
    print(f"\nRequesting: {url}")
    req = urllib.request.Request(url, method="GET")
    resp = urllib.request.urlopen(req, timeout=15)
    raw = json.loads(resp.read())
    datas = raw.get("datas", raw)
    print(f"Response: {json.dumps(raw, indent=2)}")

    host = datas.get("rest_server_https")
    assert host, f"No rest_server_https in response: {raw}"
    print(f"Host: {host}")


def test_userconf_live():
    """Step 2: Call userconf directly with the token."""
    creds = _get_creds()
    if not creds:
        pytest.skip("Set AKUVOX_AUTH_TOKEN, AKUVOX_TOKEN, AKUVOX_PHONE env vars")
    auth_token, token, phone, subdomain = creds

    # First get host from rest_server API (result wraps in "datas")
    rest_url = f"https://gate.{subdomain}.akuvox.com:8600/rest_server"
    req = urllib.request.Request(rest_url, method="GET")
    resp = urllib.request.urlopen(req, timeout=15)
    rest_raw = json.loads(resp.read())
    rest_datas = rest_raw.get("datas", rest_raw)
    host = rest_datas.get("rest_server_https")
    assert host, f"No rest_server_https: {rest_raw}"
    print(f"Host: {host}")

    # Now call userconf
    url = f"https://{host}/userconf?token={token}"
    print(f"\nUserconf URL: {url.replace(token, token[:8]+'***')}")
    headers = {
        "Host": host,
        "X-AUTH-TOKEN": token,
        "Connection": "keep-alive",
        "api-version": "6.6",
        "Accept": "*/*",
        "User-Agent": "VBell/6.61.2 (iPhone; iOS 16.6; Scale/3.00)",
        "Accept-Language": "en-AU;q=1, he-AU;q=0.9, ru-RU;q=0.8",
        "x-cloud-lang": "en"
    }
    print(f"Headers: {json.dumps({k: (v[:8]+'***' if k in ('X-AUTH-TOKEN',) else v) for k, v in headers.items()}, indent=2)}")
    data = json.dumps({}).encode()

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    resp = urllib.request.urlopen(req, timeout=15)
    resp_data = json.loads(resp.read())
    print(f"\nResponse: {json.dumps(resp_data, indent=2)}")

    assert resp_data.get("result") == 0, f"Failed: {resp_data}"
    # userconf may return datas directly or wrapped
    inner = resp_data.get("datas", resp_data)
    assert "dev_list" in inner, f"No dev_list in response: {json.dumps(resp_data, indent=2)}"
    print(f"\n== userconf SUCCESS! {len(inner.get('dev_list', []))} devices found ==")
    for dev in inner.get("dev_list", []):
        print(f"   - {dev.get('location', '?')} (MAC: {dev.get('mac', '?')})")
    if "app_conf" in inner:
        print(f"   Project: {inner['app_conf'].get('project_name', '?')}")
