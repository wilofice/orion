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
from fastapi.testclient import TestClient

from app.quick_insert_event_app import app as event_app
import app.quick_insert_event_app as event_module


def test_post_event(monkeypatch):
    def dummy_schedule(startDate, startTime, endDate, endTime, topic, description, tz):
        return {"id": "1", "_id": "1", "summary": topic}
    monkeypatch.setattr(event_module, "schedule_event", dummy_schedule)
    client = TestClient(event_app)
    payload = {
        "startTime": "10:00:00",
        "endTime": "11:00:00",
        "startDate": "2023-01-01",
        "endDate": "2023-01-01",
        "topic": "test",
        "description": "d",
        "attendees": []
    }
    resp = client.post("/events/", json=payload)
    assert resp.status_code == 200
    assert resp.json()["message"] == "Event creation request received"

