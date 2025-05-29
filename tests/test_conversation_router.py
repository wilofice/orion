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


def test_list_conversations_mismatch(monkeypatch):
    client = create_test_client(verify_user_id="other")
    monkeypatch.setattr("app.conversation_router.get_user_conversations", lambda uid: [])
    resp = client.get("/conversations/test_user")
    assert resp.status_code == 403
