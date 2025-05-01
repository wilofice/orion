# Example Usage section from app/scheduler_logic.py
from app.scheduler_logic import filter_slots_by_preferences

# --- Example Usage ---
if __name__ == '__main__':
    import logging
    from datetime import datetime, timedelta, date, time
    import pytz # For robust timezone handling

    # Assume models.py etc. are importable and defined as in previous steps
    # If running this block standalone, you'd need the actual model definitions
    # or dummy versions like these:
    try:
        # Attempt to import actual models first
        from models import UserPreferences, DayOfWeek, TimeSlot
    except ImportError:
        print("Warning: Could not import models. Using dummy classes for example.")
        # Define dummy classes if models.py is not available
        class TimeSlot:
            def __init__(self, start_time, end_time):
                if not isinstance(start_time, datetime) or not isinstance(end_time, datetime): raise TypeError("Times must be datetime")
                if start_time.tzinfo is None or end_time.tzinfo is None: raise ValueError("Times must be timezone-aware")
                if end_time <= start_time: raise ValueError("End must be after start")
                self.start_time, self.end_time = start_time, end_time
            @property
            def duration(self): return self.end_time - self.start_time
            def __lt__(self, other): return self.start_time < other.start_time # For sorting
            def __repr__(self): return f"DummyTimeSlot({self.start_time.isoformat()}, {self.end_time.isoformat()})"
        class DayOfWeek: MONDAY=0; TUESDAY=1; WEDNESDAY=2; THURSDAY=3; FRIDAY=4; SATURDAY=5; SUNDAY=6 # Dummy enum
        class UserPreferences:
             def __init__(self, user_id, time_zone, working_hours, days_off):
                 self.user_id = user_id
                 self.time_zone = time_zone
                 self.working_hours = working_hours
                 self.days_off = days_off
                 # Add other fields with defaults if needed by filter_slots_by_preferences

    # Import the function to be tested (assuming it's in the same file)
    # If filter_slots_by_preferences is in scheduler_logic.py and you run this file:
    # from __main__ import filter_slots_by_preferences
    # If running separately, you might need:
    # from scheduler_logic import filter_slots_by_preferences

    # --- Setup ---
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    tz_pref = "Europe/Paris" # Example timezone
    user_tz = None
    user_zi = None
    now_dt_naive = datetime.now().replace(minute=0, second=0, microsecond=0)

    try:
        # Try using zoneinfo (Python 3.9+)
        from zoneinfo import ZoneInfo
        user_zi = ZoneInfo(tz_pref)
        now_dt = now_dt_naive.replace(tzinfo=user_zi) # Make naive datetime timezone-aware
        logger.info("Using zoneinfo for timezone handling.")
    except (ImportError, KeyError):
         # Fallback to pytz
         logger.warning("zoneinfo not available or timezone key error, falling back to pytz.")
         try:
             user_tz = pytz.timezone(tz_pref)
             now_dt = user_tz.localize(now_dt_naive) # Make naive datetime timezone-aware using pytz
             logger.info("Using pytz for timezone handling.")
         except Exception as e:
             logger.error(f"Failed to initialize timezone with pytz: {e}")
             # Handle error appropriately, maybe exit or use UTC fallback
             from datetime import timezone
             now_dt = now_dt_naive.replace(tzinfo=timezone.utc)
             logger.warning("Falling back to UTC.")


    # --- Example User Preferences ---
    prefs = UserPreferences(
        user_id="test_user",
        time_zone=tz_pref,
        working_hours={
            DayOfWeek.MONDAY: (time(9, 0), time(12, 30)), # Morning block
            DayOfWeek.TUESDAY: (time(14, 0), time(17, 0)), # Afternoon block
            # Wednesday undefined -> never available
        },
        days_off=[date(2025, 5, 6)] # Assume May 6th, 2025 is a Tuesday
                                      # This makes Tuesday unavailable despite working_hours
    )

    # --- Example Raw Free Slots (Simulating output from Task 2's calculate_free_slots) ---
    # Helper function to create timezone-aware datetime using the determined method
    def make_aware(dt_naive: datetime) -> datetime:
        if user_zi: # Prefer zoneinfo if available
            return dt_naive.replace(tzinfo=user_zi)
        elif user_tz: # Fallback to pytz
            return user_tz.localize(dt_naive)
        else: # Fallback to UTC if both failed
            from datetime import timezone
            return dt_naive.replace(tzinfo=timezone.utc)

    # Example: Assuming now_dt corresponds to Monday May 5th, 2025 for the example dates
    base_date = date(2025, 5, 5)

    raw_free = [
        # Monday morning (partially overlaps prefs: 8-10 -> 9-10)
        TimeSlot(start_time=make_aware(datetime.combine(base_date, time(8, 0))),
                 end_time=make_aware(datetime.combine(base_date, time(10, 0)))),
        # Monday afternoon (outside prefs: 13-15 -> none)
        TimeSlot(start_time=make_aware(datetime.combine(base_date, time(13, 0))),
                 end_time=make_aware(datetime.combine(base_date, time(15, 0)))),
        # All of Tuesday (will be removed by days_off)
        TimeSlot(start_time=make_aware(datetime.combine(base_date + timedelta(days=1), time(0, 0))),
                 end_time=make_aware(datetime.combine(base_date + timedelta(days=2), time(0, 0)))), # Tuesday
        # All of Wednesday (will be removed by lack of working hours)
        TimeSlot(start_time=make_aware(datetime.combine(base_date + timedelta(days=2), time(0, 0))),
                 end_time=make_aware(datetime.combine(base_date + timedelta(days=3), time(0, 0)))), # Wednesday
        # Monday spanning working hours (11-14 -> 11-12:30)
        TimeSlot(start_time=make_aware(datetime.combine(base_date, time(11, 0))),
                 end_time=make_aware(datetime.combine(base_date, time(14, 0)))),
    ]


    print("\n--- Raw Free Slots ---")
    for slot in raw_free: print(slot)
    print("--- End Raw Free Slots ---")


    # --- Filter Slots by Preferences ---
    # Make sure the filter_slots_by_preferences function is defined or imported above
    final_available_slots = filter_slots_by_preferences(raw_free, prefs)


    # --- Print Results ---
    print("\n--- Final Available Slots (After Preferences Filter) ---")
    if final_available_slots:
        for slot in final_available_slots:
            # Format output for clarity
            start_f = slot.start_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')
            end_f = slot.end_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')
            print(f"Start: {start_f}, End: {end_f}, Duration: {slot.duration}")
    else:
        print("No slots available after filtering.")
    print("--- End Final Available Slots ---")
