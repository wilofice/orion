import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "app"))
os.environ.setdefault("GOOGLE_CLIENT_ID_IOS", "ios")
os.environ.setdefault("GOOGLE_CLIENT_ID_ANDROID", "android")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
os.environ.setdefault("ENCRYPTION_KEY_HEX", "0"*64)
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.chat_router as chat_router
from app.models import ChatRequest, ChatResponse, ResponseStatus

class DummySessionManager:
    async def get_history(self, session_id):
        return []
    async def append_turn(self, session_id, turn):
        pass
    async def create_session(self, user_id):
        return "session_created"

class DummyCalendarClient:
    pass

@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(chat_router.router)
    return app


def test_root_endpoint(test_app):
    client = TestClient(test_app)
    resp = client.get("/chat/")
    assert resp.status_code == 200
    assert resp.json()["message"].startswith("Orion")


def test_create_user_success(test_app):
    client = TestClient(test_app)
    payload = {"user_id": "new_user", "email": "a@b.c", "password": "pw"}
    resp = client.post("/chat/users/create", json=payload)
    assert resp.status_code == 200
    assert resp.json()["user"]["user_id"] == "new_user"


def test_create_user_exists(test_app):
    client = TestClient(test_app)
    payload = {"user_id": "existing_user", "email": "a@b.c", "password": "pw"}
    resp = client.post("/chat/users/create", json=payload)
    assert resp.status_code == 500


def test_process_chat_prompt(monkeypatch, test_app):
    async def dummy_handle_chat_request(**kwargs):
        return ChatResponse(session_id="s1", status=ResponseStatus.COMPLETED, response_text="done")

    monkeypatch.setattr(chat_router, "handle_chat_request", dummy_handle_chat_request)
    monkeypatch.setattr(chat_router, "verify_token", lambda credentials: "user_from_token")
    monkeypatch.setattr(chat_router, "get_session_manager", lambda: DummySessionManager())
    monkeypatch.setattr(chat_router, "get_gemini_client", lambda: object())
    monkeypatch.setattr(chat_router, "get_tool_executor", lambda: object())
    monkeypatch.setattr(chat_router, "get_calendar_client", lambda email: DummyCalendarClient())

    client = TestClient(test_app)
    payload = {"user_id": "user_from_token", "session_id": None, "prompt_text": "hi"}
    resp = client.post("/chat/prompt", json=payload, headers={"Authorization": "Bearer abc"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == ResponseStatus.COMPLETED

