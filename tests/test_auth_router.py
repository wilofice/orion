import uuid
from unittest.mock import AsyncMock
from tests.conftest import create_test_client


def test_connect_google_calendar_success(monkeypatch):
    client = create_test_client()
    
    # Create a valid JWT ID token with email
    import base64
    import json
    id_token_payload = {"email": "test@example.com", "sub": "google123"}
    encoded_payload = base64.urlsafe_b64encode(json.dumps(id_token_payload).encode()).decode().rstrip("=")
    id_token = f"header.{encoded_payload}.signature"

    tokens = {
        "access_token": "g_access",
        "refresh_token": "g_refresh",
        "expires_in": 3600,
        "scope": "scope",
        "id_token": id_token,
    }

    class DummyResponse:
        def json(self):
            return tokens

        def raise_for_status(self):
            pass

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def post(self, url, data=None, headers=None):
            return DummyResponse()

    monkeypatch.setattr("app.auth_router.httpx.AsyncClient", lambda: DummyClient())
    monkeypatch.setattr("app.auth_router.save_user_tokens", lambda **kwargs: "success")
    monkeypatch.setattr("app.auth_router.get_decrypted_user_tokens", lambda uid: tokens)
    monkeypatch.setattr("app.auth_router.encrypt_token", lambda token, key: (b"iv", b"ct", b"tag"))
    monkeypatch.setattr("app.auth_router.decrypt_token", lambda *a, **kw: "token")
    monkeypatch.setattr("app.auth_router.create_access_token", lambda data: "jwt_token")
    monkeypatch.setattr("app.auth_router.uuid.uuid4", lambda: uuid.UUID("00000000-0000-0000-0000-000000000001"))
    monkeypatch.setattr("app.auth_router.get_user_id_by_email", lambda email: None)  # New user
    monkeypatch.setattr("app.auth_router.save_user_email_mapping", lambda email, user_id: "success")

    payload = {
        "authorization_code": "code",
        "platform": "ios",
        "code_verifier": "ver",
        "redirect_uri": "http://localhost",
    }
    response = client.post("/auth/google/connect", json={"payload": payload})
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "jwt_token"
    assert data["user_id"] == "00000000-0000-0000-0000-000000000001"


def test_connect_google_calendar_existing_user(monkeypatch):
    client = create_test_client()
    
    # Create a valid JWT ID token with email
    import base64
    import json
    id_token_payload = {"email": "existing@example.com", "sub": "google456"}
    encoded_payload = base64.urlsafe_b64encode(json.dumps(id_token_payload).encode()).decode().rstrip("=")
    id_token = f"header.{encoded_payload}.signature"

    tokens = {
        "access_token": "g_access",
        "refresh_token": "g_refresh",
        "expires_in": 3600,
        "scope": "scope",
        "id_token": id_token,
    }

    class DummyResponse:
        def json(self):
            return tokens

        def raise_for_status(self):
            pass

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def post(self, url, data=None, headers=None):
            return DummyResponse()

    monkeypatch.setattr("app.auth_router.httpx.AsyncClient", lambda: DummyClient())
    monkeypatch.setattr("app.auth_router.save_user_tokens", lambda **kwargs: "success")
    monkeypatch.setattr("app.auth_router.get_decrypted_user_tokens", lambda uid: tokens)
    monkeypatch.setattr("app.auth_router.encrypt_token", lambda token, key: (b"iv", b"ct", b"tag"))
    monkeypatch.setattr("app.auth_router.decrypt_token", lambda *a, **kw: "token")
    monkeypatch.setattr("app.auth_router.create_access_token", lambda data: "jwt_token")
    # Return existing user ID
    monkeypatch.setattr("app.auth_router.get_user_id_by_email", lambda email: "existing-user-id-123")
    monkeypatch.setattr("app.auth_router.save_user_email_mapping", lambda email, user_id: "success")

    payload = {
        "authorization_code": "code",
        "platform": "android",
        "code_verifier": "ver",
        "redirect_uri": "http://localhost",
    }
    response = client.post("/auth/google/connect", json={"payload": payload})
    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "jwt_token"
    assert data["user_id"] == "existing-user-id-123"  # Should use existing ID


def test_connect_google_calendar_invalid_platform(monkeypatch):
    client = create_test_client()
    # patch network functions though they won't be used
    monkeypatch.setattr("app.auth_router.httpx.AsyncClient", AsyncMock)
    payload = {
        "authorization_code": "code",
        "platform": "windows",
        "code_verifier": "ver",
        "redirect_uri": "http://localhost",
    }
    response = client.post("/auth/google/connect", json={"payload": payload})
    assert response.status_code == 400


def test_disconnect_google_calendar(monkeypatch):
    client = create_test_client()
    monkeypatch.setattr("app.auth_router.delete_user_tokens", lambda uid: True)
    response = client.post("/auth/auth/google/disconnect")
    assert response.status_code == 200
    assert "Successfully" in response.json()["message"]


def test_list_google_calendars(monkeypatch):
    client = create_test_client()
    monkeypatch.setattr("app.auth_router.get_decrypted_user_tokens", lambda uid: {"access_token": "tok", "access_token_expires_at": 9999999999})
    monkeypatch.setattr("app.auth_router.refresh_google_access_token", AsyncMock(return_value="newtok"))
    response = client.get("/auth/calendar/meta/list-calendars")
    assert response.status_code == 200


def test_refresh_token(monkeypatch):
    client = create_test_client()
    monkeypatch.setattr("app.auth_router.refresh_google_access_token", AsyncMock(return_value="newtok"))
    response = client.post("/auth/auth/google/refresh-test")
    assert response.status_code == 200
    assert "new_access_token_snippet" in response.json()


def test_get_current_user_info():
    client = create_test_client()
    response = client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["user_id"] == "test_user"
