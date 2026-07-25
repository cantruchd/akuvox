import pytest
from unittest.mock import MagicMock

# Logic giả lập đơn giản không cần import HA
def process_response(response_json):
    if "result" in response_json:
        if response_json["result"] == 0:
            return response_json.get("datas", response_json)
        return None
    if "code" in response_json:
        if response_json["code"] == 0:
            return response_json.get("data", response_json)
        return []
    return None

def test_process_json_result_0_datas():
    assert process_response({"result": 0, "datas": {"k": "v"}}) == {"k": "v"}

def test_process_json_result_0_no_datas():
    assert process_response({"result": 0, "token": "abc"}) == {"result": 0, "token": "abc"}

def test_process_json_code_0_data():
    assert process_response({"code": 0, "data": {"k": "v"}}) == {"k": "v"}

def test_process_json_unknown():
    assert process_response({"unknown": "data"}) is None
