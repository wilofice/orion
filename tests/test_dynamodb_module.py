import pytest
from cryptography.exceptions import InvalidTag
from app import dynamodb


def test_encrypt_decrypt_roundtrip():
    key = b"0" * 32
    iv, ct, tag = dynamodb.encrypt_token("secret", key)
    assert isinstance(iv, bytes) and isinstance(ct, bytes) and isinstance(tag, bytes)
    result = dynamodb.decrypt_token(iv, ct, tag, key)
    assert result == "secret"


def test_encrypt_invalid_input():
    key = b"0" * 32
    with pytest.raises(TypeError):
        dynamodb.encrypt_token(123, key)
    with pytest.raises(ValueError):
        dynamodb.encrypt_token("", key)


def test_decrypt_invalid_tag():
    key = b"1" * 32
    iv, ct, tag = dynamodb.encrypt_token("data", key)
    with pytest.raises(InvalidTag):
        dynamodb.decrypt_token(iv, ct, b"bad" * 8, key)


def test_update_user_preferences_invokes_table(monkeypatch):
    called = {}

    class DummyTable:
        def update_item(self, *a, **kw):
            called["yes"] = True

    monkeypatch.setattr(dynamodb, "user_preferences_table", DummyTable())
    result = dynamodb.update_user_preferences("user", {"theme": "dark"})
    assert result == "success"
    assert called == {"yes": True}
