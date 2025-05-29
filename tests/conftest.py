import os
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure the repository root (which contains the ``app`` package) is on
# ``sys.path``. Some modules import ``settings_v1`` from the root, so the
# root must be discoverable during tests.
REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
for path in (str(REPO_ROOT), str(APP_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

# Ensure required environment variables for settings
os.environ.setdefault("GOOGLE_CLIENT_ID_IOS", "dummy")
os.environ.setdefault("GOOGLE_CLIENT_ID_ANDROID", "dummy")
os.environ.setdefault("ENCRYPTION_KEY_HEX", "0"*64)

# Prevent boto3 from attempting network calls when modules import DynamoDB
import boto3

class _DummyTable:
    def __getattr__(self, item):
        def _dummy(*args, **kwargs):
            return None
        return _dummy


class _DummyResource:
    def Table(self, name):
        return _DummyTable()

boto3.resource = lambda *args, **kwargs: _DummyResource()

from app.core import security
from app import auth_router, chat_router, conversation_router, events_router, user_preferences_router


def create_test_client(verify_user_id: str = "test_user", current_user: dict | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(auth_router.router)
    app.include_router(chat_router.router)
    app.include_router(conversation_router.router)
    app.include_router(events_router.router)
    app.include_router(user_preferences_router.router)

    async def override_verify_token(credentials=None):
        return verify_user_id

    async def override_get_current_user(credentials=None):
        return current_user or {"user_id": verify_user_id, "email": "test@example.com"}

    # Override authentication dependencies used across routers
    app.dependency_overrides[security.verify_token] = override_verify_token
    app.dependency_overrides[security.get_current_user] = override_get_current_user
    app.dependency_overrides[auth_router.get_current_user] = override_get_current_user
    app.dependency_overrides[events_router.verify_token] = override_verify_token
    app.dependency_overrides[conversation_router.verify_token] = override_verify_token
    app.dependency_overrides[chat_router.verify_token] = override_verify_token
    app.dependency_overrides[user_preferences_router.verify_token] = override_verify_token

    client = TestClient(app)
    # Provide a default authorization header so HTTPBearer does not reject requests
    client.headers.update({"Authorization": "Bearer testtoken"})
    return client
