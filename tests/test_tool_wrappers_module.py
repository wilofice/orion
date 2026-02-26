import datetime
import pytz

from app.tool_wrappers import (
    parse_datetime_flexible,
    parse_timedelta_minutes,
    GetAvailableSlotsWrapper,
)
from app.models import TimeSlot

TZ = pytz.timezone("UTC")


def test_parse_datetime_flexible():
    dt = parse_datetime_flexible("2024-01-01T10:00:00+00:00", TZ)
    assert dt == datetime.datetime(2024, 1, 1, 10, 0, tzinfo=TZ)
    dt2 = parse_datetime_flexible("2024-01-01 12:00", TZ)
    assert dt2.tzinfo == TZ and dt2.hour == 12
    assert parse_datetime_flexible("bad", TZ) is None
    assert parse_datetime_flexible("", TZ) is None


def test_parse_timedelta_minutes():
    assert parse_timedelta_minutes(30) == datetime.timedelta(minutes=30)
    assert parse_timedelta_minutes(0) is None
    assert parse_timedelta_minutes(None) is None


def test_available_slots_filters_and_grouping():
    wrapper = GetAvailableSlotsWrapper()
    slots = [
        TimeSlot(start_time=datetime.datetime(2024, 1, 1, 9, 0, tzinfo=TZ), end_time=datetime.datetime(2024, 1, 1, 10, 0, tzinfo=TZ)),
        TimeSlot(start_time=datetime.datetime(2024, 1, 1, 11, 0, tzinfo=TZ), end_time=datetime.datetime(2024, 1, 1, 11, 30, tzinfo=TZ)),
        TimeSlot(start_time=datetime.datetime(2024, 1, 6, 9, 0, tzinfo=TZ), end_time=datetime.datetime(2024, 1, 6, 10, 0, tzinfo=TZ)),
    ]
    dur = datetime.timedelta(minutes=45)
    filtered = wrapper._filter_slots_by_duration(slots, dur)
    assert filtered == [slots[0], slots[2]]

    no_weekends = wrapper._filter_slots_by_weekends(slots, False)
    assert all(s.start_time.weekday() < 5 for s in no_weekends)

    grouped = wrapper._group_slots_by_day(slots[:2])
    assert set(grouped.keys()) == {"2024-01-01"}
    assert len(grouped["2024-01-01"]) == 2
