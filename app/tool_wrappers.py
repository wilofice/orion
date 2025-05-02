# app/tool_wrappers.py

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, time, date
from typing import Dict, Any, Optional, List, Tuple

import pytz # For timezone handling
from dateutil.parser import parse as dateutil_parse # For flexible datetime parsing
from pydantic import BaseModel, ValidationError, Field, field_validator

# Attempt to import dependent models and interfaces
try:
    # Interfaces from Task 5
    from tool_interface import ExecutionContext, ExecutorToolResult, ToolResultStatus
    # Core models from Task 1
    from models import WantToDoActivity, TimeSlot, ActivityCategory, UserPreferences, DayOfWeek
    # Core logic functions (conceptual imports)
    from scheduler_logic import schedule_want_to_do_basic, ConflictInfo # Need ConflictInfo if handling conflicts here
    # Calendar client interface (needed from context)
    from calendar_api import AbstractCalendarClient
except ImportError as e:
    # Fallback for running script directly or if structure differs
    print("Warning: Could not import dependent modules. Using dummy classes/functions.")

# --- Abstract Base Class for Tool Wrappers (Task 6.1) ---

class ToolWrapper(ABC):
    """
    Abstract Base Class for all tool wrappers.
    Defines the interface for the Tool Executor to interact with specific tool logic.
    """
    tool_name: str # Subclasses should define the tool name they handle

    @abstractmethod
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        """
        Executes the tool's logic with the provided arguments and context.

        Args:
            args: Dictionary of arguments parsed from the Gemini function call.
                  Types will likely be simple (str, int, float, bool).
            context: The ExecutionContext containing user preferences, calendar client, etc.

        Returns:
            An ExecutorToolResult indicating the outcome (success, error, clarification).
        """
        pass

    def _create_success_result(self, result_data: Dict[str, Any]) -> ExecutorToolResult:
        """Helper to create a success result."""
        return ExecutorToolResult(name=self.tool_name, status=ToolResultStatus.SUCCESS, result=result_data)

    def _create_error_result(self, error_details: str, result_data: Optional[Dict[str, Any]] = None) -> ExecutorToolResult:
        """Helper to create an error result."""
        return ExecutorToolResult(name=self.tool_name, status=ToolResultStatus.ERROR, error_details=error_details, result=result_data)

    def _create_clarification_result(self, prompt: str, result_data: Optional[Dict[str, Any]] = None) -> ExecutorToolResult:
        """Helper to create a clarification result."""
        return ExecutorToolResult(name=self.tool_name, status=ToolResultStatus.CLARIFICATION_NEEDED, clarification_prompt=prompt, result=result_data)


# --- Argument Parsing Utilities ---

def parse_datetime_flexible(dt_str: str, user_tz: pytz.BaseTzInfo) -> Optional[datetime]:
    """
    Parses a date/time string using dateutil.parser and makes it timezone-aware.
    Handles relative terms like "tomorrow", "next Tuesday 3pm".

    Args:
        dt_str: The date/time string from Gemini.
        user_tz: The user's timezone.

    Returns:
        A timezone-aware datetime object or None if parsing fails.
    """
    if not dt_str:
        return None
    try:
        # fuzzy=True might be too lenient, consider False first
        dt_naive = dateutil_parse(dt_str, fuzzy=False)
        # If parsing yields only a date, assume start of day? Or require time?
        # For now, assume parser gets time if specified.
        # Make the parsed datetime timezone-aware using user's timezone
        dt_aware = user_tz.localize(dt_naive, is_dst=None) # is_dst=None handles ambiguity
        return dt_aware
    except (ValueError, OverflowError, TypeError) as e:
        logging.getLogger(__name__).warning(f"Could not parse datetime string '{dt_str}': {e}")
        return None

def parse_timedelta_minutes(minutes: Optional[int]) -> Optional[timedelta]:
    """Parses duration in minutes to timedelta."""
    if minutes is None or minutes <= 0:
        return None
    try:
        return timedelta(minutes=int(minutes))
    except (ValueError, TypeError):
        return None

# --- Concrete Tool Wrapper Implementation (Task 6.2) ---

class ScheduleActivityWrapperArgs(BaseModel):
    """Input validation model for schedule_activity arguments."""
    title: str = Field(..., description="The title of the task or event.")
    start_time_str: Optional[str] = Field(None, description="Requested start time (e.g., 'tomorrow 9am', '2025-05-10 14:00').")
    end_time_str: Optional[str] = Field(None, description="Requested end time.")
    duration_minutes: Optional[int] = Field(None, gt=0, description="Requested duration in minutes (alternative to end_time).")
    category_str: Optional[str] = Field(None, description="Category hint (e.g., 'WORK', 'PERSONAL').")
    priority: Optional[int] = Field(None, ge=1, le=10, description="Priority hint (1-10).")
    deadline_str: Optional[str] = Field(None, description="Optional deadline string.")

    @field_validator('category_str')
    @classmethod
    def check_category(cls, v: Optional[str]):
        """Validate if the category string matches enum values (case-insensitive)."""
        if v and v.upper() not in ActivityCategory.__members__:
            raise ValueError(f"Invalid category. Choose from: {list(ActivityCategory.__members__.keys())}")
        return v

class ScheduleActivityWrapper(ToolWrapper):
    """
    Wrapper for the 'schedule_activity' tool.
    Handles parsing arguments, calling core scheduling logic, and formatting results.
    """
    tool_name = "schedule_activity"
    logger = logging.getLogger(__name__)
    def _handle_fixed_time_scheduling(
        self,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: Optional[str],
        context: ExecutionContext
    ) -> ExecutorToolResult:
        """Handles scheduling when specific start and end times are provided."""
        self.logger.info(f"Handling fixed time schedule request: '{title}' from {start_time} to {end_time}")

        try:
            # 1. Check for conflicts directly on the calendar
            # We check for *any* busy slot within the exact requested time frame.
            # We assume get_busy_slots returns events that *overlap* the given range.
            # We need to be careful about events ending exactly when the new one starts, or vice-versa.
            # Let's check for busy slots slightly within the range to avoid boundary issues.
            check_start = start_time + timedelta(microseconds=1)
            check_end = end_time - timedelta(microseconds=1)

            # Ensure check range is valid if duration is very short
            if check_start >= check_end:
                 check_start = start_time
                 check_end = end_time

            self.logger.debug(f"Checking for conflicts between {check_start} and {check_end}")
            # Get busy slots from the calendar client : make method call async later
            conflicting_busy_slots = context.calendar_client.get_busy_slots(
                calendar_id='primary', # Assuming primary for now
                start_time=check_start,
                end_time=check_end
            )

            if conflicting_busy_slots:
                # Conflict detected
                conflict_details = ", ".join([f"'{getattr(slot.activity_obj, 'title', 'Unknown Event')}' ({slot.start_time.time()} - {slot.end_time.time()})"
                                            for slot in conflicting_busy_slots if hasattr(slot, 'activity_obj')]) # Check if dummy slots have activity_obj
                if not conflict_details: conflict_details = f"{len(conflicting_busy_slots)} existing event(s)" # Fallback message
                error_msg = f"Cannot schedule '{title}' at the requested time because it conflicts with: {conflict_details}."
                self.logger.warning(error_msg)
                return self._create_error_result(error_msg, result_data={"conflicts": [str(s) for s in conflicting_busy_slots]}) # Pass conflict details if needed

            # 2. No conflict, add the event to the calendar
            self.logger.info(f"No conflicts found. Adding event '{title}' to calendar.")
            # Conceptual call - AbstractCalendarClient needs an add_event method
            created_event_details = context.calendar_client.add_event(
                title=title,
                start_time=start_time,
                end_time=end_time,
                description=description
                # Potentially add attendees, location etc. if provided in args
            )

            self.logger.info(f"Event added successfully: {created_event_details}")
            return self._create_success_result({
                "message": f"OK. Scheduled '{title}'.",
                "event_id": created_event_details.get("id"),
                "event_link": created_event_details.get("htmlLink"),
                "scheduled_start": start_time.isoformat(),
                "scheduled_end": end_time.isoformat(),
            })

        except Exception as e:
            self.logger.exception(f"Error during fixed-time scheduling for '{title}': {e}")
            return self._create_error_result(f"An internal error occurred while scheduling the fixed-time event: {e}")



    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")

        # 1. Validate arguments using Pydantic model
        try:
            validated_args = ScheduleActivityWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            error_msg = f"Invalid arguments provided for scheduling: {e.errors()}"
            clarification = f"I couldn't understand the details for scheduling. Please clarify: {e.errors()}"
            return self._create_clarification_result(clarification, result_data={"validation_errors": e.errors()})

        # 2. Convert simple types to domain types
        try:
            user_tz = pytz.timezone(context.preferences.time_zone)
        except Exception as e:
             self.logger.error(f"Invalid timezone in user preferences: {context.preferences.time_zone} - {e}")
             return self._create_error_result(f"Invalid timezone configuration found in your preferences: {context.preferences.time_zone}")

        start_time: Optional[datetime] = parse_datetime_flexible(validated_args.start_time_str, user_tz)
        end_time: Optional[datetime] = parse_datetime_flexible(validated_args.end_time_str, user_tz)
        duration: Optional[timedelta] = parse_timedelta_minutes(validated_args.duration_minutes)
        deadline: Optional[datetime] = parse_datetime_flexible(validated_args.deadline_str, user_tz)
        category: Optional[ActivityCategory] = ActivityCategory(validated_args.category_str.upper()) if validated_args.category_str else None
        description: Optional[str] = validated_args.description # Get description

        # --- Logic to determine task parameters ---

        # Scenario 1: Fixed start and end time provided
        if start_time and end_time:
            if end_time <= start_time:
                return self._create_error_result("End time must be after start time.")
            # --- Call helper for fixed time scheduling ---
            return self._handle_fixed_time_scheduling(
                title=validated_args.title,
                start_time=start_time,
                end_time=end_time,
                description=description,
                context=context
            )

        # Scenario 2: Start time and duration provided
        elif start_time and duration:
            calculated_end_time = start_time + duration
            # --- Call helper for fixed time scheduling ---
            return self._handle_fixed_time_scheduling(
                title=validated_args.title,
                start_time=start_time,
                end_time=calculated_end_time,
                description=description,
                context=context
            )

        # Scenario 3: Duration provided, find available slot (Core flexible scheduling)
        elif duration:
            estimated_duration = duration
            self.logger.info(f"Scheduling flexible task: duration {duration}")
            # This is the main path using our existing scheduler logic

            if not category:
                # Ask for category if flexible scheduling is requested without one
                return self._create_clarification_result("Please specify a category (e.g., WORK, PERSONAL) for this task.")
            priority = validated_args.priority or 5 # Default priority

            activity_to_schedule = WantToDoActivity(
                title=validated_args.title,
                description=description, # Pass description
                estimated_duration=estimated_duration,
                priority=priority,
                category=category,
                deadline=deadline,
            )

            # 3. Call core logic
            try:
                # 3a. Get available slots (using Task 5 logic via calendar client)
                query_start = datetime.now(user_tz) # Or context-aware start
                query_end = query_start + timedelta(days=7) # Configurable range
                self.logger.info(f"Fetching available slots from {query_start} to {query_end}")
                # Ensure calendar_client is awaited if its methods are async
                available_slots = context.calendar_client.get_available_time_slots(
                    preferences=context.preferences,
                    start_time=query_start,
                    end_time=query_end
                )
                self.logger.info(f"Found {len(available_slots)} available slots matching preferences.")

                if not available_slots:
                     return self._create_error_result(f"No available time slots found in the next 7 days matching your preferences.")

                # 3b. Run the basic scheduler (Task 4)
                scheduled_map, unscheduled = schedule_want_to_do_basic(
                    want_to_do_list=[activity_to_schedule],
                    available_slots=available_slots
                )

                # 4. Format the result
                if activity_to_schedule.id in scheduled_map:
                    scheduled_slot = scheduled_map[activity_to_schedule.id]
                    self.logger.info(f"Successfully scheduled '{activity_to_schedule.title}' at {scheduled_slot.start_time}")

                    # TODO: Persist the scheduled event (e.g., add to Google Calendar via calendar_client, update task status in DB)
                    # Example conceptual call:
                    created_event_details = context.calendar_client.add_event(
                    title=activity_to_schedule.title,
                         start_time=scheduled_slot.start_time,
                         end_time=scheduled_slot.end_time,
                         description=activity_to_schedule.description
                    )
                    event_id = created_event_details.get("id")
                    event_link = created_event_details.get("htmlLink")
                    # Simulate success for now
                    event_id = event_id
                    event_link = event_link

                    return self._create_success_result({
                        "message": f"OK. Scheduled '{activity_to_schedule.title}'.",
                        "activity_id": activity_to_schedule.id,
                        "event_id": event_id, # Add event ID from calendar
                        "event_link": event_link, # Add link from calendar
                        "scheduled_start": scheduled_slot.start_time.isoformat(),
                        "scheduled_end": scheduled_slot.end_time.isoformat(),
                        "category": activity_to_schedule.category.value,
                    })
                else:
                    self.logger.warning(f"Could not schedule '{activity_to_schedule.title}' - no suitable slot found.")
                    return self._create_error_result(f"Could not find a suitable time slot for '{activity_to_schedule.title}' with duration {activity_to_schedule.estimated_duration}.")

            except Exception as e:
                self.logger.exception(f"Core logic execution failed: {e}")
                return self._create_error_result(f"An internal error occurred while trying to schedule: {e}")

        # Scenario 4: Insufficient information
        else:
            self.logger.warning("Insufficient information provided for scheduling.")
            return self._create_clarification_result("Please provide at least a duration, or specific start/end times for the activity.")



# --- Tool Registry (Conceptual) ---
# The Tool Executor would use a registry like this to find the correct wrapper.
TOOL_REGISTRY: Dict[str, ToolWrapper] = {
    "schedule_activity": ScheduleActivityWrapper(),
    # Add other tool wrappers here as they are created
}

# --- Example Usage ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Dummy context objects for example
    class DummyPrefs(UserPreferences):
        user_id: str = "user_123"
        time_zone: str = "Europe/Paris" # Must be valid pytz timezone
        working_hours: Dict[DayOfWeek, Tuple[time, time]] = {}# Add dummy hours if needed
        days_off: List[date] = []
    class DummyClient(AbstractCalendarClient):
        def authenticate(self): pass
        def get_busy_slots(self, *args, **kwargs): return []
        def calculate_free_slots(self, busy_slots, start_time, end_time):
             # Basic demo: return the whole period if no busy slots
             if not busy_slots: return [TimeSlot(start_time=start_time, end_time=end_time)]
             return [] # Simplified
        def get_available_time_slots(self, preferences, start_time, end_time, **kwargs):
            # Simulate Task 5 filtering - for demo, return a few slots
             tz = pytz.timezone(preferences.time_zone)
             now = datetime.now(tz)
             return [
                 TimeSlot(start_time=now+timedelta(hours=1), end_time=now+timedelta(hours=3)),
                 TimeSlot(start_time=now+timedelta(hours=5), end_time=now+timedelta(hours=8)),
             ]

    exec_context = ExecutionContext(
        user_id="user_123",
        preferences=DummyPrefs(),
        calendar_client=DummyClient()
    )

    # --- Test Cases ---
    print("\n--- Test Case 1: Flexible Scheduling (Duration) ---")
    args1 = {"title": "Write report", "duration_minutes": 90, "category_str": "WORK", "priority": 8}
    wrapper1 = ScheduleActivityWrapper()
    result1 = wrapper1.run(args1, exec_context)
    print(result1.model_dump_json(indent=2))

    print("\n--- Test Case 2: Fixed Time ---")
    args2 = {"title": "Fixed Meeting", "start_time_str": "tomorrow 10am", "end_time_str": "tomorrow 11am"}
    wrapper2 = ScheduleActivityWrapper()
    result2 = wrapper2.run(args2, exec_context)
    print(result2.model_dump_json(indent=2))

    print("\n--- Test Case 3: Insufficient Info ---")
    args3 = {"title": "Vague Task"}
    wrapper3 = ScheduleActivityWrapper()
    result3 = wrapper3.run(args3, exec_context)
    print(result3.model_dump_json(indent=2))

    print("\n--- Test Case 4: Validation Error (Bad Category) ---")
    args4 = {"title": "My Hobby", "duration_minutes": 60, "category_str": "FUN"}
    wrapper4 = ScheduleActivityWrapper()
    result4 = wrapper4.run(args4, exec_context)
    print(result4.model_dump_json(indent=2))

    print("\n--- Test Case 5: Validation Error (No Title) ---")
    args5 = {"duration_minutes": 60, "category_str": "WORK"}
    wrapper5 = ScheduleActivityWrapper()
    result5 = wrapper5.run(args5, exec_context)
    print(result5.model_dump_json(indent=2))

