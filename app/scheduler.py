# app/scheduler_logic.py

from zoneinfo import ZoneInfo  # Python 3.9+
import logging
import bisect
from datetime import datetime, timedelta, date, time
from typing import List, Tuple, Dict, Optional

from pydantic import BaseModel, Field
import pytz # For robust timezone handling
# Assuming models and timeline are in the same app directory or accessible
try:
    from models import MustDoActivity, WantToDoActivity, TimeSlot, ActivityStatus, PriorityLevel, ActivityCategory, \
    UserPreferences, DayOfWeek
    from timeline import ScheduleTimeline, ScheduledItem
except ImportError:
    # Fallback for running script directly or if structure differs
    print("Warning: Could not import models or timeline. Using dummy classes.")
    # Define dummy classes if needed for standalone testing
    class MustDoActivity:
        def __init__(self, id, title, start_time, end_time, priority):
            self.id = id
            self.title = title
            self.start_time = start_time
            self.end_time = end_time
            self.priority = priority
    class ScheduleTimeline:
        def __init__(self): self._items = []
        def add_item(self, item): print(f"Dummy Add: {item}")
        def find_overlapping_items(self, start, end): print(f"Dummy Find Overlap: {start}-{end}"); return []
    class ScheduledItem:
         def __init__(self, start_time, end_time, activity_obj):
            self.start_time = start_time
            self.end_time = end_time
            self.activity_obj = activity_obj


# --- Conflict Information Structure (Sub-task 3.3) ---

class ConflictInfo(BaseModel):
    """
    Represents a detected conflict between two scheduled activities.
    """
    activity_id_1: str = Field(..., description="ID of the first conflicting activity.")
    activity_id_2: str = Field(..., description="ID of the second conflicting activity (the one being added).")
    activity_title_1: Optional[str] = Field(None, description="Title of the first activity (for context).")
    activity_title_2: Optional[str] = Field(None, description="Title of the second activity (for context).")
    overlap_start: datetime = Field(..., description="Start time of the overlapping period.")
    overlap_end: datetime = Field(..., description="End time of the overlapping period.")

    def __str__(self):
        t1 = self.activity_title_1 or self.activity_id_1
        t2 = self.activity_title_2 or self.activity_id_2
        return (f"Conflict between '{t1}' and '{t2}' from "
                f"{self.overlap_start.isoformat()} to {self.overlap_end.isoformat()}")


# --- Must-Do Placement Function (Sub-task 3.2) ---

def place_must_do_activities(
    must_do_list: List[MustDoActivity],
    timeline: ScheduleTimeline
) -> Tuple[ScheduleTimeline, List[ConflictInfo]]:
    """
    Places MustDoActivity objects onto the timeline, detecting conflicts.

    Iterates through the provided list of MustDo activities, attempts to place
    each onto the timeline. If an activity conflicts with any item already
    on the timeline, it is not placed, and a ConflictInfo object is generated.

    Args:
        must_do_list: A list of MustDoActivity objects to be placed.
        timeline: The ScheduleTimeline instance to place activities onto.
                  This object will be modified in place if activities are added.

    Returns:
        A tuple containing:
        - The updated ScheduleTimeline object (modified in place).
        - A list of ConflictInfo objects detailing any detected conflicts.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Placing {len(must_do_list)} MustDo activities onto the timeline.")

    conflicts: List[ConflictInfo] = []

    # Sort activities by start time to process them chronologically
    # This isn't strictly necessary for correctness due to overlap checks,
    # but can be slightly more intuitive.
    sorted_must_do_list = sorted(must_do_list, key=lambda act: act.start_time)

    for activity in sorted_must_do_list:
        logger.debug(f"Attempting to place '{activity.title}' ({activity.start_time} - {activity.end_time})")

        # Find items on the timeline that overlap with the current activity's time range
        overlapping_items = timeline.find_overlapping_items(activity.start_time, activity.end_time)

        if overlapping_items:
            # Conflict detected! Record conflict info for each overlap.
            logger.warning(f"Conflict detected for '{activity.title}'!")
            for existing_item in overlapping_items:
                # Calculate exact overlap period
                overlap_start = max(activity.start_time, existing_item.start_time)
                overlap_end = min(activity.end_time, existing_item.end_time)

                # Ensure overlap is valid (should be, if find_overlapping_items is correct)
                if overlap_start < overlap_end:
                    # Get IDs and titles for the ConflictInfo object
                    existing_activity = existing_item.activity_obj
                    existing_id = getattr(existing_activity, 'id', 'unknown_existing')
                    existing_title = getattr(existing_activity, 'title', 'N/A')
                    activity_id = getattr(activity, 'id', 'unknown_new') # Should always have ID from model
                    activity_title = getattr(activity, 'title', 'N/A') # Should always have title

                    conflict = ConflictInfo(
                        activity_id_1=existing_id,
                        activity_id_2=activity_id,
                        activity_title_1=existing_title,
                        activity_title_2=activity_title,
                        overlap_start=overlap_start,
                        overlap_end=overlap_end
                    )
                    conflicts.append(conflict)
                    logger.debug(f"  - Conflict details: {conflict}")

            # As per instructions, do not add the conflicting activity to the timeline
            logger.info(f"Skipping placement of '{activity.title}' due to conflict(s).")

        else:
            # No conflicts, add the activity to the timeline
            logger.debug(f"No conflicts found for '{activity.title}'. Adding to timeline.")
            try:
                scheduled_item = ScheduledItem(
                    start_time=activity.start_time,
                    end_time=activity.end_time,
                    activity_obj=activity
                )
                timeline.add_item(scheduled_item)
            except ValueError as e:
                 logger.error(f"Error creating ScheduledItem for '{activity.title}': {e}. Skipping.")
            except Exception as e:
                 logger.exception(f"Unexpected error adding '{activity.title}' to timeline: {e}. Skipping.")


    logger.info(f"Finished placing MustDo activities. Found {len(conflicts)} conflict(s). Timeline now has {len(timeline)} items.")
    # Return the timeline (which was modified in place) and the list of conflicts
    return timeline, conflicts

def schedule_want_to_do_basic(
    want_to_do_list: List[WantToDoActivity],
    available_slots: List[TimeSlot]
) -> Tuple[Dict[str, TimeSlot], List[WantToDoActivity]]:
    """
    Schedules WantToDoActivity items into available slots using a basic first-fit algorithm.

    Iterates through activities sorted by priority and places them into the
    first available slot that is long enough. Modifies the available_slots list
    as slots are consumed.

    Args:
        want_to_do_list: List of WantToDoActivity objects, assumed to be pre-sorted
                         by priority (highest priority first).
        available_slots: List of TimeSlot objects representing free time, assumed
                         to be sorted by start time. This list will be modified.

    Returns:
        A tuple containing:
        - scheduled_mapping: A dictionary mapping scheduled activity IDs to the
                             TimeSlot they were assigned.
        - unscheduled_activities: A list of WantToDoActivity objects that could
                                  not be scheduled.
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Attempting to schedule {len(want_to_do_list)} WantToDo activities using first-fit.")

    scheduled_mapping: Dict[str, TimeSlot] = {}
    unscheduled_activities: List[WantToDoActivity] = []
    # Work on a copy of the slots list to avoid modifying the original input list directly
    # This also makes modifying the list during iteration safer.
    remaining_slots = sorted(available_slots, key=lambda s: s.start_time) # Ensure sorted

    for activity in want_to_do_list:
        logger.debug(f"Trying to schedule '{activity.title}' (duration: {activity.estimated_duration}, priority: {activity.priority})")
        is_scheduled = False
        # Iterate through the *indices* of remaining_slots because we might modify the list
        slot_index = 0
        while slot_index < len(remaining_slots):
            slot = remaining_slots[slot_index]
            logger.debug(f"  Checking slot: {slot.start_time} - {slot.end_time} (duration: {slot.duration})")

            # Check if the slot is long enough
            if slot.duration >= activity.estimated_duration:
                logger.debug(f"    Slot is suitable. Scheduling '{activity.title}'.")
                # Schedule the activity at the beginning of this slot
                assigned_slot = TimeSlot(
                    start_time=slot.start_time,
                    end_time=slot.start_time + activity.estimated_duration
                )
                scheduled_mapping[activity.id] = assigned_slot
                activity.status = ActivityStatus.SCHEDULED # Update status

                # Update the remaining_slots list
                if slot.duration == activity.estimated_duration:
                    # Slot is fully consumed, remove it
                    remaining_slots.pop(slot_index)
                    logger.debug(f"    Removed fully consumed slot.")
                    # Do not increment slot_index, the next item is now at the current index
                else:
                    # Slot is partially consumed, update its start time
                    try:
                        updated_slot = TimeSlot(
                            start_time=assigned_slot.end_time,
                            end_time=slot.end_time
                        )
                        remaining_slots[slot_index] = updated_slot
                        logger.debug(f"    Updated partially consumed slot to: {updated_slot.start_time} - {updated_slot.end_time}")
                    except ValueError as e:
                         # This might happen if rounding leads to end <= start
                         logger.warning(f"Could not update slot after scheduling {activity.title} due to invalid resulting times ({assigned_slot.end_time} / {slot.end_time}). Removing slot instead. Error: {e}")
                         remaining_slots.pop(slot_index)
                         # Do not increment slot_index
                         continue # Skip incrementing index

                    # Increment index because we modified the current slot, not removed it
                    slot_index += 1

                is_scheduled = True
                break # Move to the next activity
            else:
                # Slot is too short, move to the next slot
                logger.debug(f"    Slot is too short.")
                slot_index += 1

        if not is_scheduled:
            logger.info(f"Could not find a suitable slot for '{activity.title}'. Marking as unscheduled.")
            unscheduled_activities.append(activity)
            # Ensure status is TODO if it failed scheduling
            activity.status = ActivityStatus.TODO

    logger.info(f"Finished scheduling WantToDo activities. Scheduled: {len(scheduled_mapping)}, Unscheduled: {len(unscheduled_activities)}.")
    return scheduled_mapping, unscheduled_activities


# --- Example Usage ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    # Assume models.py and timeline.py exist and are importable
    tz = ZoneInfo("America/New_York")
    now_dt = datetime.now(tz).replace(minute=0, second=0, microsecond=0)
    timeline = ScheduleTimeline()

    # --- Example MustDo Placement (from previous example) ---
    must_do_1 = MustDoActivity(id="m1", title="Meeting A", start_time=now_dt + timedelta(hours=9),
                               end_time=now_dt + timedelta(hours=10), priority=PriorityLevel.HIGH)
    must_do_2 = MustDoActivity(id="m4", title="Lunch", start_time=now_dt + timedelta(hours=12),
                               end_time=now_dt + timedelta(hours=13), priority=PriorityLevel.MEDIUM)
    must_do_tasks_for_placement = [must_do_1, must_do_2]
    timeline, _ = place_must_do_activities(must_do_tasks_for_placement, timeline)
    print("\n--- Timeline after MustDo ---")
    for item in timeline.get_all_items(): print(item)
    print("--- End Timeline ---")

    # --- Define Available Slots (Example - In reality, this comes from Task 2/5) ---
    # Simulate getting available slots around the MustDos
    available = [
        TimeSlot(start_time=now_dt + timedelta(hours=8), end_time=now_dt + timedelta(hours=9)),  # 1 hr before Meeting A
        TimeSlot(start_time=now_dt + timedelta(hours=10), end_time=now_dt + timedelta(hours=12)),
        # 2 hrs between Meeting A and Lunch
        TimeSlot(start_time=now_dt + timedelta(hours=13), end_time=now_dt + timedelta(hours=16)),  # 3 hrs after Lunch
    ]
    print("\n--- Initial Available Slots ---")
    for slot in available: print(slot)
    print("--- End Available Slots ---")

    # --- Define WantToDo Activities ---
    task1_p10 = WantToDoActivity(id="w1", title="Write Report", estimated_duration=timedelta(hours=1, minutes=30),
                                 priority=10, category=ActivityCategory.WORK)
    task2_p8 = WantToDoActivity(id="w2", title="Review PRs", estimated_duration=timedelta(hours=1), priority=8,
                                category=ActivityCategory.WORK)
    task3_p9 = WantToDoActivity(id="w3", title="Go for Run", estimated_duration=timedelta(hours=1), priority=9,
                                category=ActivityCategory.EXERCISE)
    task4_p5_long = WantToDoActivity(id="w4", title="Deep Work Session", estimated_duration=timedelta(hours=4),
                                     priority=5, category=ActivityCategory.WORK)  # Too long for any single slot
    task5_p7 = WantToDoActivity(id="w5", title="Plan Weekend", estimated_duration=timedelta(minutes=30), priority=7,
                                category=ActivityCategory.PERSONAL)

    # Sort by priority (descending) as required by the function's input spec
    want_to_do_tasks = sorted(
        [task1_p10, task2_p8, task3_p9, task4_p5_long, task5_p7],
        key=lambda t: t.priority,
        reverse=True
    )
    print("\n--- WantToDo Tasks (Sorted by Priority) ---")
    for task in want_to_do_tasks: print(f"- {task.title} (Prio: {task.priority}, Dur: {task.estimated_duration})")
    print("--- End WantToDo Tasks ---")

    # --- Run Want-to-Do Scheduling ---
    scheduled_map, unscheduled_list = schedule_want_to_do_basic(want_to_do_tasks, available)

    # --- Print Results ---
    print("\n--- WantToDo Scheduling Results ---")
    print("Scheduled Activities:")
    if scheduled_map:
        for task_id, slot in scheduled_map.items():
            # Find original task object for title
            task_title = "Unknown"
            for task in want_to_do_tasks:
                if task.id == task_id:
                    task_title = task.title
                    break
            print(
                f"- {task_title} ({task_id}): {slot.start_time.strftime('%H:%M')} - {slot.end_time.strftime('%H:%M')}")
    else:
        print("  (None)")

    print("\nUnscheduled Activities:")
    if unscheduled_list:
        for task in unscheduled_list:
            print(f"- {task.title} (Prio: {task.priority}, Dur: {task.estimated_duration})")
    else:
        print("  (None)")
    print("--- End Results ---")


    # --- Preference-Based Slot Filtering (Task 5.1 / 5.2) ---

def filter_slots_by_preferences(
        raw_free_slots: List[TimeSlot],
        preferences: UserPreferences,
        # query_start and query_end are implicitly defined by the range of raw_free_slots
) -> List[TimeSlot]:
    """
    Filters a list of raw free TimeSlots based on user preferences
    (working hours, days off).

    Args:
        raw_free_slots: List of TimeSlot objects representing free time,
                        assumed to be sorted by start time.
        preferences: The UserPreferences object for the user.

    Returns:
        A filtered list of TimeSlot objects representing periods that are
        both free on the calendar AND align with user preferences.

    Raises:
        ValueError: If timeslots or preferences contain invalid timezone info.
        pytz.UnknownTimeZoneError: If preferences.time_zone is invalid.
    """
    filter_logger = logging.getLogger(__name__)
    filter_logger.info(f"Filtering {len(raw_free_slots)} raw free slots by user preferences.")

    if not raw_free_slots:
        return []

    try:
        user_tz = pytz.timezone(preferences.time_zone)
    except pytz.UnknownTimeZoneError as e:
        filter_logger.error(f"Invalid timezone in preferences: {preferences.time_zone}")
        raise e

    filtered_slots: List[TimeSlot] = []

    for raw_slot in raw_free_slots:
        filter_logger.debug(f"Processing raw slot: {raw_slot.start_time} - {raw_slot.end_time}")
        # Ensure slot times are in user's timezone for daily comparison
        slot_start_user_tz = raw_slot.start_time.astimezone(user_tz)
        slot_end_user_tz = raw_slot.end_time.astimezone(user_tz)

        # Iterate through each day covered by the slot
        current_day = slot_start_user_tz.date()
        end_date = slot_end_user_tz.date()

        # Handle slots ending exactly at midnight (belong to the previous day)
        if slot_end_user_tz.time() == time.min:
            end_date = (slot_end_user_tz - timedelta(microseconds=1)).date()

        while current_day <= end_date:
            filter_logger.debug(f"  Checking day: {current_day}")

            # Check if this day is a day off
            is_day_off = current_day in preferences.days_off
            if is_day_off:
                filter_logger.debug(f"    Day {current_day} is a day off. Skipping.")
                current_day += timedelta(days=1)
                continue  # Skip to the next day within the slot

            # Get working hours for this weekday
            weekday = DayOfWeek(current_day.weekday())  # Monday is 0
            working_times = preferences.working_hours.get(weekday)

            if not working_times:
                filter_logger.debug(f"    No working hours defined for {current_day} ({weekday.name}). Skipping.")
                current_day += timedelta(days=1)
                continue  # Skip to the next day within the slot

            # Define the user's available interval for this specific day
            work_start_time, work_end_time = working_times
            day_work_start_dt = user_tz.localize(datetime.combine(current_day, work_start_time))
            day_work_end_dt = user_tz.localize(datetime.combine(current_day, work_end_time))

            # Calculate the intersection of the current raw slot with the working hours of this day
            # Intersection start = max(slot_start, work_start)
            # Intersection end = min(slot_end, work_end)
            intersection_start = max(slot_start_user_tz, day_work_start_dt)
            intersection_end = min(slot_end_user_tz, day_work_end_dt)

            # If intersection_end > intersection_start, there is a valid overlap
            if intersection_end > intersection_start:
                filter_logger.debug(
                    f"    Found valid intersection on {current_day}: {intersection_start} - {intersection_end}")
                try:
                    filtered_slots.append(TimeSlot(start_time=intersection_start, end_time=intersection_end))
                except ValueError as e:
                    # Should not happen if logic is correct, but catch just in case
                    filter_logger.error(f"Error creating TimeSlot for intersection on {current_day}: {e}")

            current_day += timedelta(days=1)

    filter_logger.info(f"Filtered down to {len(filtered_slots)} slots matching preferences.")
    # Sort final list as intersections might be added out of order if a slot spans multiple days
    filtered_slots.sort(key=lambda s: s.start_time)
    return filtered_slots
    # Optional: Add scheduled WantToDo items to the main timeline
    # (Requires WantToDoActivity to be compatible with timeline item structure or wrapping)
    # print("\n--- Final Timeline (Conceptual) ---")
    # final_timeline = timeline # Start with MustDos
    # for task_id, slot in scheduled_map.items():
    #      # Find the original task object
    #      scheduled_task = next((task for task in want_to_do_tasks if task.id == task_id), None)
    #      if scheduled_task:
    #          try:
    #              final_timeline.add_item(ScheduledItem(slot.start_time, slot.end_time, scheduled_task))
    #          except Exception as e:
    #              logger.error(f"Could not add scheduled WantToDo '{scheduled_task.title}' to final timeline: {e}")
    # for item in sorted(final_timeline.get_all_items(), key=lambda i: i.start_time):
    #     print(item)
    # print("--- End Final Timeline ---")

