"""Live test for servers_list API."""
import os
import json
import urllib.request
import pytest


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


def test_servers_list_live():
    creds = _get_creds()
    if not creds:
        pytest.skip("Set AKUVOX_AUTH_TOKEN, AKUVOX_TOKEN, AKUVOX_PHONE env vars")
    auth_token, token, phone, subdomain = creds
    obfuscated = obfuscate(phone)
    print(f"Phone: {phone} -> obfuscated: {obfuscated}")

    # Try both body formats like the code does
    bodies = [
        {"label": "without_passwd", "body": {"auth_token": auth_token, "token": token, "user": obfuscated}},
        {"label": "with_passwd", "body": {"auth_token": auth_token, "passwd": auth_token, "token": token, "user": obfuscated}},
    ]

    for item in bodies:
        label = item["label"]
        body = item["body"]
        url = f"https://gate.{subdomain}.akuvox.com:8600/servers_list"
        data = json.dumps(body).encode()
        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "x-auth-token": token,
            "api-version": "6.6",
            "x-cloud-lang": "en",
            "user-agent": "VBell/6.61.2 (iPhone; iOS 16.6; Scale/3.00)",
            "accept-language": "en-AU;q=1, he-AU;q=0.9, ru-RU;q=0.8"
        }

        print(f"\n--- {label} ---")
        print(f"URL: {url}")
        print(f"Body: {json.dumps({k: (v[:8]+'***' if k != 'user' and len(v) > 8 else v) for k, v in body.items()})}")
        print(f"Headers x-auth-token: {token[:8]}***")

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            resp_data = json.loads(resp.read())
            print(f"Response: {json.dumps(resp_data, indent=2)}")
        except urllib.error.HTTPError as e:
            print(f"HTTP Error: {e.code} {e.reason}")
            print(f"Response: {e.read().decode()}")
        except Exception as e:
            print(f"Error: {e}")
