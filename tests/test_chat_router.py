from unittest.mock import AsyncMock
from tests.conftest import create_test_client
from app.models import ChatResponse, ResponseStatus


def test_chat_prompt_success(monkeypatch):
    client = create_test_client()

    async def mock_handle_chat_request(**kwargs):
        return ChatResponse(session_id="s1", status=ResponseStatus.COMPLETED, response_text="hi")

    monkeypatch.setattr("app.chat_router.handle_chat_request", mock_handle_chat_request)
    monkeypatch.setattr("app.chat_router.get_session_manager", lambda: object())
    monkeypatch.setattr("app.chat_router.get_gemini_client", lambda: object())
    monkeypatch.setattr("app.chat_router.get_tool_executor", lambda: object())
    monkeypatch.setattr("app.chat_router.get_calendar_client", lambda email: object())

    payload = {"user_id": "test_user", "session_id": "s1", "prompt_text": "hello"}
    response = client.post("/chat/prompt", json=payload)
    assert response.status_code == 200
    assert response.json()["session_id"] == "s1"


def test_chat_prompt_mismatch_user(monkeypatch):
    client = create_test_client(verify_user_id="other_user")
    monkeypatch.setattr("app.chat_router.handle_chat_request", AsyncMock())
    payload = {"user_id": "test_user", "session_id": "s1", "prompt_text": "hello"}
    response = client.post("/chat/prompt", json=payload)
    assert response.status_code == 403


def test_chat_root():
    client = create_test_client()
    response = client.get("/chat/")
    assert response.status_code == 200
    assert "Orion" in response.json()["message"]
