"""Tests for phone number obfuscation logic (copied from api.py)."""

def obfuscate(phone_number):
    import re
    num_str = re.sub(r'\D', '', str(phone_number))
    if not num_str:
        return 0
    transformed_str = ""
    for digit_char in num_str:
        digit = int(digit_char)
        transformed_digit = (digit + 3) % 10
        transformed_str += str(transformed_digit)
    return int(transformed_str)


def test_sg_number():
    assert obfuscate("88607189") == 11930412

def test_with_country_code():
    assert obfuscate("988607189") == 211930412

def test_empty():
    assert obfuscate("") == 0

def test_none():
    assert obfuscate(None) == 0

def test_spaces_dashes():
    assert obfuscate("9123 4567") == 24567890

def test_plus_country():
    assert obfuscate("6591234567") == 9824567890
