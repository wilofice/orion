import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), "app"))
import pytest
os.environ.setdefault("GOOGLE_CLIENT_ID_IOS", "ios")
os.environ.setdefault("GOOGLE_CLIENT_ID_ANDROID", "android")
os.environ.setdefault("ENCRYPTION_KEY_HEX", "0"*64)
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.conversation_router as conversation_router

@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(conversation_router.router)
    return app


def test_list_user_conversations(monkeypatch, test_app):
    sample = [
        {"session_id": "s1", "user_id": "u1", "history": []},
        {"session_id": "s2", "user_id": "u1", "history": []},
    ]
    monkeypatch.setattr(conversation_router, "get_user_conversations", lambda uid: sample)
    client = TestClient(test_app)
    resp = client.get("/conversations/u1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["session_id"] == "s1"

