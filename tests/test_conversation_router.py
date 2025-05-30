from tests.conftest import create_test_client


def test_list_conversations_success(monkeypatch):
    client = create_test_client()

    sample_items = [
        {"session_id": "s1", "user_id": "test_user", "history": []},
        {"session_id": "s2", "user_id": "test_user", "history": []},
    ]
    monkeypatch.setattr("app.conversation_router.get_user_conversations", lambda uid: sample_items)

    resp = client.get("/conversations/test_user")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 2


def test_list_conversations_filters_roles(monkeypatch):
    client = create_test_client()

    # Include different role types in history
    sample_items = [{
        "session_id": "s1",
        "user_id": "test_user",
        "history": [
            {"role": "USER", "parts": ["Hello"], "timestamp": "2024-01-01T00:00:00Z"},
            {"role": "AI", "parts": ["Hi there!"], "timestamp": "2024-01-01T00:00:01Z"},
            {"role": "FUNCTION", "parts": ["Function result"], "timestamp": "2024-01-01T00:00:02Z"},
            {"role": "SYSTEM", "parts": ["System message"], "timestamp": "2024-01-01T00:00:03Z"},
            {"role": "USER", "parts": ["Another message"], "timestamp": "2024-01-01T00:00:04Z"},
            {"role": "AI", "parts": ["Another response"], "timestamp": "2024-01-01T00:00:05Z"},
        ]
    }]
    monkeypatch.setattr("app.conversation_router.get_user_conversations", lambda uid: sample_items)

    resp = client.get("/conversations/test_user")
    assert resp.status_code == 200
    conversations = resp.json()
    assert len(conversations) == 1
    
    # Check that only USER and AI messages are included
    history = conversations[0]["history"]
    assert len(history) == 4  # Should only have 2 USER and 2 AI messages
    
    # Verify all messages are either USER or AI
    for turn in history:
        assert turn["role"] in ["USER", "AI"]


def test_list_conversations_mismatch(monkeypatch):
    client = create_test_client(verify_user_id="other")
    monkeypatch.setattr("app.conversation_router.get_user_conversations", lambda uid: [])
    resp = client.get("/conversations/test_user")
    assert resp.status_code == 403
