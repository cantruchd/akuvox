"""Integration tests for Akuvox servers_list API.
Requires env vars: AKUVOX_AUTH_TOKEN, AKUVOX_TOKEN, AKUVOX_PHONE

Usage:
  $env:AKUVOX_AUTH_TOKEN="..." python -m pytest tests/test_api_integration.py -v
"""
import os
import json
import urllib.request
import urllib.error
import pytest


def obfuscate(num):
    return "".join(str((int(d) + 3) % 10) for d in str(num))


def _get_creds():
    auth_token = os.environ.get("AKUVOX_AUTH_TOKEN")
    token = os.environ.get("AKUVOX_TOKEN")
    phone = os.environ.get("AKUVOX_PHONE")
    if not all([auth_token, token, phone]):
        return None
    return auth_token, token, phone


def test_obfuscation():
    """Verify obfuscation matches known result."""
    result = obfuscate("88607189")
    assert result == "11930412", f"Expected 11930412, got {result}"


class TestServersList:
    """Live API tests (requires env vars)."""

    BODIES = [
        {"label": "without_passwd", "body": None},
        {"label": "with_passwd", "body": None},
    ]

    def test_servers_list_without_passwd(self):
        creds = _get_creds()
        if not creds:
            pytest.skip("Set AKUVOX_AUTH_TOKEN, AKUVOX_TOKEN, AKUVOX_PHONE env vars")
        auth_token, token, phone = creds
        body = {"auth_token": auth_token, "token": token, "user": obfuscate(phone)}
        self._call(body)

    def test_servers_list_with_passwd(self):
        creds = _get_creds()
        if not creds:
            pytest.skip("Set AKUVOX_AUTH_TOKEN, AKUVOX_TOKEN, AKUVOX_PHONE env vars")
        auth_token, token, phone = creds
        body = {"auth_token": auth_token, "passwd": auth_token, "token": token, "user": obfuscate(phone)}
        self._call(body)

    def _call(self, body):
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            "https://gate.scloud.akuvox.com:8600/servers_list",
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-auth-token": body["token"],
                "api-version": "6.6",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=15)
        resp_body = json.loads(resp.read())
        print(f"\nRequest body: {json.dumps({k: v[:8]+'***' if k != 'user' else v for k, v in body.items()})}")
        print(f"Response: {json.dumps(resp_body, indent=2)}")
        assert resp_body.get("result") == 0, f"Failed: {resp_body}"
        assert "datas" in resp_body, f"No datas in response: {resp_body}"
        data = resp_body["datas"]
        assert "rtmp_server" in data, f"No rtmp_server in response: {data}"
        print(f"RTSP IP: {data['rtmp_server'].split(':')[0]}")
