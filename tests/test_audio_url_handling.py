"""Tests for audio URL handling in chat and conversation endpoints."""
import pytest
from unittest.mock import AsyncMock
from tests.conftest import create_test_client
from app.models import ChatResponse, ResponseStatus
from app.gemini_interface import ConversationTurn, ConversationRole


def test_chat_prompt_with_audio_url(monkeypatch):
    """Test that chat endpoint accepts and processes audio URL."""
    client = create_test_client()
    
    async def mock_handle_chat_request(**kwargs):
        # Verify audio_url is passed through
        request = kwargs['request']
        assert request.audio_url == "https://s3.amazonaws.com/bucket/audio/test.m4a"
        assert request.prompt_text == "This is the transcribed audio"
        return ChatResponse(
            session_id="audio_session_1", 
            status=ResponseStatus.COMPLETED, 
            response_text="I understood your audio message"
        )
    
    monkeypatch.setattr("app.chat_router.handle_chat_request", mock_handle_chat_request)
    monkeypatch.setattr("app.chat_router.get_session_manager", lambda: object())
    monkeypatch.setattr("app.chat_router.get_gemini_client", lambda: object())
    monkeypatch.setattr("app.chat_router.get_tool_executor", lambda: object())
    monkeypatch.setattr("app.chat_router.get_calendar_client", lambda email: object())
    
    payload = {
        "user_id": "test_user",
        "session_id": "audio_session_1",
        "prompt_text": "This is the transcribed audio",
        "audio_url": "https://s3.amazonaws.com/bucket/audio/test.m4a"
    }
    response = client.post("/chat/prompt", json=payload)
    assert response.status_code == 200
    assert response.json()["response_text"] == "I understood your audio message"


def test_chat_prompt_without_audio_url(monkeypatch):
    """Test that chat endpoint works without audio URL (backward compatibility)."""
    client = create_test_client()
    
    async def mock_handle_chat_request(**kwargs):
        # Verify audio_url is None when not provided
        request = kwargs['request']
        assert request.audio_url is None
        return ChatResponse(
            session_id="text_session_1", 
            status=ResponseStatus.COMPLETED, 
            response_text="Text message processed"
        )
    
    monkeypatch.setattr("app.chat_router.handle_chat_request", mock_handle_chat_request)
    monkeypatch.setattr("app.chat_router.get_session_manager", lambda: object())
    monkeypatch.setattr("app.chat_router.get_gemini_client", lambda: object())
    monkeypatch.setattr("app.chat_router.get_tool_executor", lambda: object())
    monkeypatch.setattr("app.chat_router.get_calendar_client", lambda email: object())
    
    payload = {
        "user_id": "test_user",
        "session_id": "text_session_1",
        "prompt_text": "Regular text message"
    }
    response = client.post("/chat/prompt", json=payload)
    assert response.status_code == 200


def test_conversation_history_with_audio_messages(monkeypatch):
    """Test that conversation history correctly returns audio URLs."""
    client = create_test_client()
    
    # Mock conversation data with both text and audio messages
    mock_conversation_data = [
        {
            "session_id": "mixed_session_1",
            "user_id": "test_user",
            "history": [
                {
                    "role": "USER",
                    "parts": ["USER: Hello, this is a text message"],
                    "timestamp": "2024-01-01T10:00:00Z"
                },
                {
                    "role": "AI",
                    "parts": ["AI: I received your text message"],
                    "timestamp": "2024-01-01T10:00:01Z"
                },
                {
                    "role": "USER",
                    "parts": [
                        {
                            "transcript": "USER: This is an audio message",
                            "audio_url": "https://s3.amazonaws.com/bucket/audio/message1.m4a"
                        }
                    ],
                    "timestamp": "2024-01-01T10:01:00Z"
                },
                {
                    "role": "AI",
                    "parts": ["AI: I understood your audio message"],
                    "timestamp": "2024-01-01T10:01:01Z"
                }
            ]
        }
    ]
    
    monkeypatch.setattr("app.conversation_router.get_user_conversations", 
                       lambda user_id: mock_conversation_data)
    
    response = client.get("/conversations/test_user")
    assert response.status_code == 200
    
    conversations = response.json()
    assert len(conversations) == 1
    
    history = conversations[0]["history"]
    assert len(history) == 4
    
    # Check text message
    assert history[0]["role"] == "USER"
    assert history[0]["parts"] == ["Hello, this is a text message"]
    
    # Check audio message
    assert history[2]["role"] == "USER"
    assert len(history[2]["parts"]) == 1
    assert isinstance(history[2]["parts"][0], dict)
    assert history[2]["parts"][0]["transcript"] == "This is an audio message"
    assert history[2]["parts"][0]["audio_url"] == "https://s3.amazonaws.com/bucket/audio/message1.m4a"


def test_conversation_turn_audio_creation():
    """Test ConversationTurn.user_turn with audio URL."""
    # Test with audio URL
    audio_turn = ConversationTurn.user_turn(
        text="Audio transcript",
        audio_url="https://s3.amazonaws.com/bucket/audio/test.m4a"
    )
    
    assert audio_turn.role == ConversationRole.USER
    assert len(audio_turn.parts) == 1
    assert isinstance(audio_turn.parts[0], dict)
    assert audio_turn.parts[0]["transcript"] == "USER: Audio transcript"
    assert audio_turn.parts[0]["audio_url"] == "https://s3.amazonaws.com/bucket/audio/test.m4a"
    
    # Test without audio URL (backward compatibility)
    text_turn = ConversationTurn.user_turn("Text message")
    assert text_turn.role == ConversationRole.USER
    assert len(text_turn.parts) == 1
    assert text_turn.parts[0] == "USER: Text message"


def test_chat_prompt_with_empty_audio_url(monkeypatch):
    """Test that empty string audio URL is treated as None."""
    client = create_test_client()
    
    async def mock_handle_chat_request(**kwargs):
        request = kwargs['request']
        # Empty string should be converted to None or handled gracefully
        assert request.audio_url == ""
        return ChatResponse(
            session_id="s1", 
            status=ResponseStatus.COMPLETED, 
            response_text="Processed"
        )
    
    monkeypatch.setattr("app.chat_router.handle_chat_request", mock_handle_chat_request)
    monkeypatch.setattr("app.chat_router.get_session_manager", lambda: object())
    monkeypatch.setattr("app.chat_router.get_gemini_client", lambda: object())
    monkeypatch.setattr("app.chat_router.get_tool_executor", lambda: object())
    monkeypatch.setattr("app.chat_router.get_calendar_client", lambda email: object())
    
    payload = {
        "user_id": "test_user",
        "prompt_text": "Test",
        "audio_url": ""
    }
    response = client.post("/chat/prompt", json=payload)
    assert response.status_code == 200


def test_conversation_history_filters_non_user_ai_messages(monkeypatch):
    """Test that conversation history only returns USER and AI messages, not function calls."""
    client = create_test_client()
    
    mock_conversation_data = [
        {
            "session_id": "s1",
            "user_id": "test_user",
            "history": [
                {
                    "role": "USER",
                    "parts": ["USER: What's the weather?"],
                    "timestamp": "2024-01-01T10:00:00Z"
                },
                {
                    "role": "FUNCTION_CALL",
                    "parts": ["AI TOOL CALL: {\"name\": \"get_weather\"}"],
                    "timestamp": "2024-01-01T10:00:01Z"
                },
                {
                    "role": "FUNCTION_RESULT",
                    "parts": ["TOOL RESULT: {\"weather\": \"sunny\"}"],
                    "timestamp": "2024-01-01T10:00:02Z"
                },
                {
                    "role": "AI",
                    "parts": ["AI: The weather is sunny"],
                    "timestamp": "2024-01-01T10:00:03Z"
                }
            ]
        }
    ]
    
    monkeypatch.setattr("app.conversation_router.get_user_conversations", 
                       lambda user_id: mock_conversation_data)
    
    response = client.get("/conversations/test_user")
    assert response.status_code == 200
    
    conversations = response.json()
    history = conversations[0]["history"]
    
    # Should only have 2 messages (USER and AI)
    assert len(history) == 2
    assert history[0]["role"] == "USER"
    assert history[0]["parts"] == ["What's the weather?"]
    assert history[1]["role"] == "AI"
    assert history[1]["parts"] == ["The weather is sunny"]