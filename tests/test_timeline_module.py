import datetime
from zoneinfo import ZoneInfo

from app.timeline import ScheduledItem, ScheduleTimeline


def make_dt(hour: int, minute: int = 0):
    tz = ZoneInfo("UTC")
    return datetime.datetime(2024, 1, 1, hour, minute, tzinfo=tz)


def test_add_item_sorts_by_start_time():
    item1 = ScheduledItem(make_dt(10), make_dt(11), "A")
    item2 = ScheduledItem(make_dt(8), make_dt(9), "B")
    tl = ScheduleTimeline()
    tl.add_item(item1)
    tl.add_item(item2)
    items = tl.get_all_items()
    assert items == [item2, item1]


def test_find_overlapping_items_basic():
    tl = ScheduleTimeline()
    a = ScheduledItem(make_dt(9), make_dt(10), "A")
    b = ScheduledItem(make_dt(11), make_dt(12), "B")
    tl.add_item(a)
    tl.add_item(b)

    overlaps = tl.find_overlapping_items(make_dt(9, 30), make_dt(9, 45))
    assert overlaps == [a]

    # Adjacent range should not overlap
    assert tl.find_overlapping_items(make_dt(10), make_dt(11)) == []

    overlaps2 = tl.find_overlapping_items(make_dt(11, 30), make_dt(11, 45))
    assert overlaps2 == [b]


def test_find_overlapping_items_invalid_timezone():
    tl = ScheduleTimeline()
    naive_start = datetime.datetime(2024, 1, 1, 10)
    naive_end = datetime.datetime(2024, 1, 1, 11)
    try:
        tl.find_overlapping_items(naive_start, naive_end)
    except ValueError:
        pass
    else:
        assert False, "Expected ValueError for naive datetimes"
