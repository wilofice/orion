import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from app.calendar_client import GoogleCalendarAPIClient
from app.models import TimeSlot


def test_calculate_free_slots_basic():
    tz = ZoneInfo("UTC")
    start = datetime(2024, 1, 1, 8, 0, tzinfo=tz)
    end = datetime(2024, 1, 1, 18, 0, tzinfo=tz)
    busy = [
        TimeSlot(start_time=datetime(2024, 1, 1, 10, 0, tzinfo=tz), end_time=datetime(2024, 1, 1, 11, 0, tzinfo=tz)),
        TimeSlot(start_time=datetime(2024, 1, 1, 13, 0, tzinfo=tz), end_time=datetime(2024, 1, 1, 14, 30, tzinfo=tz)),
    ]
    client = GoogleCalendarAPIClient(token_info={"access_token": "a", "refresh_token": "r", "app_user_id": "u"})
    free = client.calculate_free_slots(busy, start, end)
    assert [(s.start_time, s.end_time) for s in free] == [
        (start, datetime(2024, 1, 1, 10, 0, tzinfo=tz)),
        (datetime(2024, 1, 1, 11, 0, tzinfo=tz), datetime(2024, 1, 1, 13, 0, tzinfo=tz)),
        (datetime(2024, 1, 1, 14, 30, tzinfo=tz), end),
    ]


def test_calculate_free_slots_validation():
    tz = ZoneInfo("UTC")
    start = datetime(2024, 1, 1, 8, 0, tzinfo=tz)
    end = datetime(2024, 1, 1, 18, 0, tzinfo=tz)
    client = GoogleCalendarAPIClient(token_info={"access_token": "a", "refresh_token": "r", "app_user_id": "u"})
    with pytest.raises(ValueError):
        client.calculate_free_slots([], start.replace(tzinfo=None), end)
    with pytest.raises(ValueError):
        client.calculate_free_slots([], start, start)
