import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "app"))
import time
os.environ.setdefault("GOOGLE_CLIENT_ID_IOS", "ios")
os.environ.setdefault("GOOGLE_CLIENT_ID_ANDROID", "android")
os.environ.setdefault("ENCRYPTION_KEY_HEX", "0"*64)
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx

import app.auth_router as auth_router

class DummyResponse:
    def __init__(self, data):
        self._data = data
    def raise_for_status(self):
        pass
    def json(self):
        return self._data

class DummyClient:
    async def __aenter__(self):
        return self
    async def __aexit__(self, exc_type, exc, tb):
        pass
    async def post(self, url, data=None, headers=None):
        return DummyResponse({"access_token": "a", "refresh_token": "r", "expires_in": 3600, "scope": "s"})

@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(auth_router.router)
    return app


def test_connect_google_calendar(monkeypatch, test_app):
    monkeypatch.setattr(httpx, "AsyncClient", lambda: DummyClient())
    monkeypatch.setattr(auth_router, "save_user_tokens", lambda **kwargs: "success")
    monkeypatch.setattr(auth_router, "get_decrypted_user_tokens", lambda uid: {"access_token": "a"})
    monkeypatch.setattr(auth_router, "encrypt_token", lambda token, key: (b"iv", b"ct", b"tag"))
    monkeypatch.setattr(auth_router, "decrypt_token", lambda iv, ct, tag, key: ct)
    monkeypatch.setattr(auth_router.uuid, "uuid4", lambda: "fixed-id")

    client = TestClient(test_app)
    payload = {
        "authorization_code": "code",
        "platform": "ios",
        "code_verifier": "ver",
        "redirect_uri": "https://example.com/cb"
    }
    resp = client.post("/auth/google/connect", json=payload)
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "fixed-id"


def test_disconnect_google_calendar(monkeypatch, test_app):
    monkeypatch.setattr(auth_router, "delete_user_tokens", lambda uid: True)
    client = TestClient(test_app)
    resp = client.post("/auth/auth/google/disconnect")
    assert resp.status_code == 200


def test_list_google_calendars(monkeypatch, test_app):
    monkeypatch.setattr(auth_router, "get_decrypted_user_tokens", lambda uid: {"access_token": "abc", "access_token_expires_at": time.time()+1000})
    client = TestClient(test_app)
    resp = client.get("/auth/calendar/meta/list-calendars")
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "dummy_user_id_123"



def test_refresh_token(monkeypatch, test_app):
    async def dummy_refresh(uid):
        return "newtoken"
    monkeypatch.setattr(auth_router, "refresh_google_access_token", dummy_refresh)
    client = TestClient(test_app)
    resp = client.post("/auth/auth/google/refresh-test")
    assert resp.status_code == 200
    assert resp.json()["new_access_token_snippet"].startswith("newtoken"[:10])

