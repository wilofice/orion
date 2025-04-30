# app/timeline.py

import bisect
from datetime import datetime, timedelta
from typing import List, Any, Optional

# Assuming models.py is in the same directory or accessible via PYTHONPATH
try:
    # Import specific activity types if needed for type hinting or logic
    from models import TimeSlot, MustDoActivity, WantToDoActivity
    ActivityObject = Any # Or Union[MustDoActivity, WantToDoActivity, ...] if defined
except ImportError:
    # Fallback for running script directly or if structure differs
    print("Warning: Could not import models. Using basic types.")
    # Define dummy classes if models are unavailable for standalone testing
    class TimeSlot: pass
    class MustDoActivity: pass
    class WantToDoActivity: pass
    ActivityObject = Any # Define ActivityObject as Any if models aren't available

class ScheduledItem:
    """
    Represents an activity placed onto the timeline.

    Stores the time boundaries and a reference to the original activity object.
    Implements comparison methods based on start_time for sorting.
    """
    def __init__(self, start_time: datetime, end_time: datetime, activity_obj: ActivityObject):
        """
        Initializes a ScheduledItem.

        Args:
            start_time: The start time of the scheduled item (timezone-aware).
            end_time: The end time of the scheduled item (timezone-aware).
            activity_obj: The original activity object (e.g., MustDoActivity) being scheduled.

        Raises:
            ValueError: If start_time or end_time are not timezone-aware,
                        or if end_time <= start_time.
        """
        if start_time.tzinfo is None or end_time.tzinfo is None:
            raise ValueError("ScheduledItem times must be timezone-aware.")
        if end_time <= start_time:
            raise ValueError("ScheduledItem end_time must be after start_time.")

        self.start_time: datetime = start_time
        self.end_time: datetime = end_time
        self.activity_obj: ActivityObject = activity_obj

    # --- Comparison methods for sorting using bisect ---
    def __lt__(self, other: 'ScheduledItem') -> bool:
        # Primarily sort by start time, then end time as a tie-breaker
        if not isinstance(other, ScheduledItem):
            return NotImplemented
        if self.start_time != other.start_time:
            return self.start_time < other.start_time
        return self.end_time < other.end_time

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ScheduledItem):
            return NotImplemented
        return (self.start_time == other.start_time and
                self.end_time == other.end_time and
                # Optionally compare activity_obj if strict equality is needed
                self.activity_obj == other.activity_obj)

    def __repr__(self) -> str:
        """Provides a developer-friendly string representation."""
        activity_title = getattr(self.activity_obj, 'title', 'N/A')
        return (f"ScheduledItem(start={self.start_time.isoformat()}, "
                f"end={self.end_time.isoformat()}, "
                f"activity='{activity_title}')")


class ScheduleTimeline:
    """
    Represents a timeline holding scheduled activities, kept sorted by start time.

    Provides methods to add items and efficiently query for overlapping items.
    """
    def __init__(self):
        """Initializes an empty schedule timeline."""
        self._items: List[ScheduledItem] = []

    def add_item(self, item: ScheduledItem) -> None:
        """
        Adds a ScheduledItem to the timeline, maintaining sorted order.

        Args:
            item: The ScheduledItem to add.
        """
        if not isinstance(item, ScheduledItem):
            raise TypeError("Can only add ScheduledItem objects to the timeline.")
        # bisect.insort maintains sorted order efficiently
        bisect.insort_left(self._items, item)

    def find_overlapping_items(self, query_start_time: datetime, query_end_time: datetime) -> List[ScheduledItem]:
        """
        Finds all items on the timeline that overlap with the given query time range.

        Overlap definition: An item overlaps if max(item.start, query.start) < min(item.end, query.end).
        The comparison is strictly '<', meaning adjacent items (item.end == query.start) do not overlap.

        Args:
            query_start_time: The start time of the query range (timezone-aware).
            query_end_time: The end time of the query range (timezone-aware).

        Returns:
            A list of ScheduledItem objects that overlap with the query range.

        Raises:
            ValueError: If query times are not timezone-aware or end <= start.
        """
        if query_start_time.tzinfo is None or query_end_time.tzinfo is None:
            raise ValueError("Query times must be timezone-aware.")
        if query_end_time <= query_start_time:
            raise ValueError("Query end_time must be after query start_time.")

        overlapping_items: List[ScheduledItem] = []

        # Optimization: Find potential start index using bisect_left.
        # We are looking for items whose end_time might be after the query_start_time.
        # Since the list is sorted by start_time, we can't directly bisect for end_time.
        # However, we can iterate starting from items whose start_time is potentially before query_end_time.
        # Create a dummy item to find the insertion point for query_end_time start.
        # Any item starting at or after this point cannot overlap with query_start_time.
        potential_end_index_marker = ScheduledItem(query_end_time, query_end_time + timedelta(microseconds=1), None)
        potential_end_index = bisect.bisect_left(self._items, potential_end_index_marker)

        # Iterate through relevant portion of the list
        for i in range(potential_end_index):
            item = self._items[i]
            # Check for overlap:
            # Condition 1: Item must start before the query ends (item.start_time < query_end_time)
            # Condition 2: Item must end after the query starts (item.end_time > query_start_time)
            if item.start_time < query_end_time and item.end_time > query_start_time:
                overlapping_items.append(item)

        return overlapping_items

    def get_all_items(self) -> List[ScheduledItem]:
        """Returns a copy of all items currently on the timeline."""
        return list(self._items) # Return a copy to prevent external modification

    def __len__(self) -> int:
        """Returns the number of items on the timeline."""
        return len(self._items)

    def __repr__(self) -> str:
        """Provides a developer-friendly string representation."""
        return f"ScheduleTimeline(items={len(self._items)})"


# --- Example Usage ---
if __name__ == '__main__':
    from datetime import timedelta
    from zoneinfo import ZoneInfo # Python 3.9+

    # Assume models.py exists and defines MustDoActivity
    try:
        from models import MustDoActivity, PriorityLevel
    except ImportError:
        # Define dummy MustDoActivity if models.py is not available
        class PriorityLevel: HIGH="HIGH"
        class MustDoActivity:
            def __init__(self, title, start_time, end_time, priority):
                self.title = title
                self.start_time = start_time
                self.end_time = end_time
                self.priority = priority
            def __repr__(self): return f"DummyMustDo(title='{self.title}')"


    tz = ZoneInfo("Europe/Paris")
    now = datetime.now(tz).replace(minute=0, second=0, microsecond=0)

    # Create some activities
    act1 = MustDoActivity(title="Meeting A", start_time=now + timedelta(hours=1), end_time=now + timedelta(hours=2), priority=PriorityLevel.HIGH)
    act2 = MustDoActivity(title="Work Block", start_time=now + timedelta(hours=3), end_time=now + timedelta(hours=5), priority=PriorityLevel.MEDIUM)
    act3 = MustDoActivity(title="Meeting B", start_time=now + timedelta(hours=4), end_time=now + timedelta(hours=4, minutes=30), priority=PriorityLevel.HIGH) # Overlaps Work Block
    act4 = MustDoActivity(title="Lunch", start_time=now + timedelta(hours=2), end_time=now + timedelta(hours=3), priority=PriorityLevel.MEDIUM) # Adjacent to Meeting A

    # Create ScheduledItems
    item1 = ScheduledItem(act1.start_time, act1.end_time, act1)
    item2 = ScheduledItem(act2.start_time, act2.end_time, act2)
    item3 = ScheduledItem(act3.start_time, act3.end_time, act3)
    item4 = ScheduledItem(act4.start_time, act4.end_time, act4)

    # Create timeline and add items
    timeline = ScheduleTimeline()
    timeline.add_item(item1)
    timeline.add_item(item2) # Added out of order, bisect handles it
    timeline.add_item(item4)
    timeline.add_item(item3) # Added out of order

    print("--- Timeline Items (Sorted) ---")
    for item in timeline.get_all_items():
        print(item)
    print("-" * 20)

    # Test overlap queries
    print("--- Overlap Queries ---")
    # Query overlapping Meeting A
    query1_start = now + timedelta(hours=1, minutes=30)
    query1_end = now + timedelta(hours=1, minutes=45)
    overlaps1 = timeline.find_overlapping_items(query1_start, query1_end)
    print(f"Overlaps with {query1_start.time()} - {query1_end.time()}: {overlaps1}")

    # Query overlapping Work Block and Meeting B
    query2_start = now + timedelta(hours=3, minutes=30)
    query2_end = now + timedelta(hours=4, minutes=15)
    overlaps2 = timeline.find_overlapping_items(query2_start, query2_end)
    print(f"Overlaps with {query2_start.time()} - {query2_end.time()}: {overlaps2}")

    # Query adjacent to Lunch and Work Block (should not overlap)
    query3_start = now + timedelta(hours=3)
    query3_end = now + timedelta(hours=3, minutes=1)
    overlaps3 = timeline.find_overlapping_items(query3_start, query3_end)
    print(f"Overlaps with {query3_start.time()} - {query3_end.time()}: {overlaps3}") # Should be Work Block

    # Query exactly matching Lunch (should overlap)
    query4_start = now + timedelta(hours=2)
    query4_end = now + timedelta(hours=3)
    overlaps4 = timeline.find_overlapping_items(query4_start, query4_end)
    print(f"Overlaps with {query4_start.time()} - {query4_end.time()}: {overlaps4}") # Should be Lunch

    # Query before all items
    query5_start = now
    query5_end = now + timedelta(minutes=30)
    overlaps5 = timeline.find_overlapping_items(query5_start, query5_end)
    print(f"Overlaps with {query5_start.time()} - {query5_end.time()}: {overlaps5}") # Should be empty

    print("-" * 20)

