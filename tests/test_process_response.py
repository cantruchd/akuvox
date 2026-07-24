"""Unit tests for process_response logic."""
import pytest
from akuvox.api import AkuvoxApiClient, AkuvoxApiClientAuthenticationError
from akuvox.data import AkuvoxData


class MockResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


def make_client():
    client = AkuvoxApiClient.__new__(AkuvoxApiClient)
    client._data = None
    client._last_error = None
    return client


class TestProcessResponse:
    def test_result_0_with_datas(self):
        client = make_client()
        resp = MockResponse(200, {"result": 0, "datas": {"key": "value"}})
        result = client.process_response(resp, "http://test.url")
        assert result == {"key": "value"}

    def test_result_0_no_datas(self):
        client = make_client()
        resp = MockResponse(200, {"result": 0, "token": "abc"})
        result = client.process_response(resp, "http://test.url")
        assert result == {"result": 0, "token": "abc"}

    def test_result_minus1_stores_error(self):
        client = make_client()
        resp = MockResponse(200, {"result": -1, "message": "invalid"})
        result = client.process_response(resp, "http://test.url")
        assert result is None
        assert client._last_error == {"result": -1, "message": "invalid"}

    def test_code_0_with_data(self):
        client = make_client()
        resp = MockResponse(200, {"code": 0, "data": {"key": "val"}})
        result = client.process_response(resp, "http://test.url")
        assert result == {"key": "val"}

    def test_code_0_no_data(self):
        client = make_client()
        resp = MockResponse(200, {"code": 0, "token": "abc"})
        result = client.process_response(resp, "http://test.url")
        assert result == {"code": 0, "token": "abc"}

    def test_code_nonzero(self):
        client = make_client()
        resp = MockResponse(200, {"code": 1})
        result = client.process_response(resp, "http://test.url")
        assert result == []

    def test_unknown_format(self):
        client = make_client()
        resp = MockResponse(200, {"foo": "bar"})
        result = client.process_response(resp, "http://test.url")
        assert result is None

    def test_http_error(self):
        client = make_client()
        resp = MockResponse(404, {"error": "not found"})
        result = client.process_response(resp, "http://test.url")
        assert result is None
        assert client._last_error is None

    def test_server_list_success_sets_rtsp_ip(self):
        """Simulate the full servers_list response parsing."""
        client = make_client()
        from data import AkuvoxData
        client._data = AkuvoxData.__new__(AkuvoxData)
        client._data.auth_token = "test_auth"
        client._data.token = "test_token"

        datas = {
            "rtmp_server": "47.84.72.232:553",
            "token": "test_token",
            "web_server": "scloud.akuvox.com",
        }
        client._data.parse_sms_login_response(datas)
        assert client._data.rtsp_ip == "47.84.72.232"
        assert client._data.token == "test_token"
