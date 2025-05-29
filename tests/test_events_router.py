import datetime
from tests.conftest import create_test_client
from app.models import TimeSlot


def test_busy_slots_success(monkeypatch):
    client = create_test_client()

    class DummyCalendar:
        def get_busy_slots(self, calendar_id, start_time, end_time):
            return [TimeSlot(start_time=start_time, end_time=end_time)]

    async def mock_get_client(user_id):
        return DummyCalendar()

    monkeypatch.setattr("app.events_router.get_calendar_client_for_user", mock_get_client)

    now = datetime.datetime.now(datetime.timezone.utc)
    resp = client.get(f"/events/test_user/busy-slots?days=1&timezone=UTC")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "test_user"
    assert data["total_busy_slots"] == 1


def test_busy_slots_timezone_error(monkeypatch):
    client = create_test_client()
    async def mock_get_client(user_id):
        return None
    monkeypatch.setattr("app.events_router.get_calendar_client_for_user", mock_get_client)
    resp = client.get("/events/test_user/busy-slots?timezone=Bad/Zone")
    assert resp.status_code == 400


def test_busy_slots_user_mismatch(monkeypatch):
    client = create_test_client(verify_user_id="other")
    resp = client.get("/events/test_user/busy-slots")
    assert resp.status_code == 403
