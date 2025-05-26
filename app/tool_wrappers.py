# app/tool_wrappers.py

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, time, date
from typing import Dict, Any, Optional, List, Tuple

import pytz # For timezone handling
from dateutil.parser import parse as dateutil_parse # For flexible datetime parsing
from pydantic import BaseModel, ValidationError, Field, field_validator
from googleapiclient.errors import HttpError

# Attempt to import dependent models and interfaces
try:
    # Interfaces from Task 5
    from tool_interface import ExecutionContext, ExecutorToolResult, ToolResultStatus
    # Core models from Task 1
    from models import WantToDoActivity, TimeSlot, ActivityCategory, UserPreferences, DayOfWeek, EnergyLevel
    # Core logic functions (conceptual imports)
    from scheduler_logic import schedule_want_to_do_basic, ConflictInfo # Need ConflictInfo if handling conflicts here
    # Calendar client interface (needed from context)
    from calendar_client import AbstractCalendarClient, GoogleCalendarAPIClient
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
    description: str = Field(..., description="Description of the tool.")
    parameters_schema: Dict[str, Any] = Field(
        ...,
        description="Schema defining the parameters for the tool."
    )

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
        if dt_naive.tzinfo is None:
            dt_aware = user_tz.localize(dt_naive, is_dst=None)  # Make it timezone-aware
        else:
            dt_aware = dt_naive.astimezone(user_tz)  # Convert to the user's timezone # is_dst=None handles ambiguity
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
    description: str = Field(..., description="The description of the task or event.")
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
    description = "Schedules an activity based on user preferences and calendar availability."
    parameters_schema = {
      "type": "object",
      "properties": {
        "title": {
          "type": "string",
          "description": "The title of the task or event or meeting or activity."
        },
        "description": {
          "type": "string",
          "description": "A very short description of the task or event or meeting or activity."
        },
        "start_time_str": {
          "type": "string",
          "description": "Requested start time in a timezone-aware format (e.g., '2025-05-10T14:00:00+02:00'). Must include full date, time, and timezone offset."
        },
        "end_time_str": {
          "type": "string",
          "description": "Requested end time in a timezone-aware format (e.g., '2025-05-10T15:00:00+02:00'). Must include full date, time, and timezone offset."
        },
        "duration_minutes": {
          "type": "integer",
          "description": "Requested duration in minutes (alternative to end_time).",
          "minimum": 1
        },
        "category_str": {
          "type": "string",
          "description": "Category hint (e.g., 'WORK', 'PERSONAL', 'LEARNING', 'EXERCISE', 'SOCIAL', 'CHORE', 'ERRAND', 'FUN', 'OTHER')."
        },
        "priority": {
          "type": "integer",
          "description": "Priority hint (1-10).",
          "minimum": 1,
          "maximum": 10
        },
        "deadline_str": {
          "type": "string",
          "description": "Optional deadline string."
        }
      },
      "required": ["title", "start_time_str", "end_time_str", "duration_minutes", "category_str"],
    }
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
                    calendar_id='primary', # Assuming primary for now
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



# --- Get Calendar Events Tool Wrapper ---

class GetCalendarEventsWrapperArgs(BaseModel):
    """Input validation model for get_calendar_events arguments."""
    days: Optional[int] = Field(7, ge=1, le=30, description="Number of days to look ahead (1-30)")
    include_all_day: Optional[bool] = Field(True, description="Whether to include all-day events")
    
class GetCalendarEventsWrapper(ToolWrapper):
    """
    Wrapper for the 'get_calendar_events' tool.
    Retrieves planned events from the user's calendar for a specified time range.
    """
    tool_name = "get_calendar_events"
    logger = logging.getLogger(__name__)
    description = "Retrieves upcoming events from the user's Google Calendar for a specified number of days."
    parameters_schema = {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Number of days to look ahead for events (1-30). Default is 7.",
                "minimum": 1,
                "maximum": 30
            },
            "include_all_day": {
                "type": "boolean",
                "description": "Whether to include all-day events in the results. Default is true."
            }
        },
        "required": []
    }
    
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")
        
        # 1. Validate arguments
        try:
            validated_args = GetCalendarEventsWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            error_msg = f"Invalid arguments for retrieving events: {e.errors()}"
            return self._create_error_result(error_msg)
        
        # 2. Get user timezone
        try:
            user_tz = pytz.timezone(context.preferences.time_zone)
        except Exception as e:
            self.logger.error(f"Invalid timezone in user preferences: {context.preferences.time_zone} - {e}")
            return self._create_error_result(f"Invalid timezone configuration: {context.preferences.time_zone}")
        
        # 3. Define time range
        now = datetime.now(user_tz)
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(days=validated_args.days)
        
        try:
            # 4. Get busy slots from calendar (these represent the user's events)
            self.logger.info(f"Fetching events from {start_time} to {end_time}")
            
            # Get calendar service to access full event details
            service = context.calendar_client._get_service()
            
            events_list = []
            page_token = None
            
            while True:
                # Call Google Calendar API directly to get full event details
                events_result = service.events().list(
                    calendarId='primary',
                    timeMin=start_time.isoformat(),
                    timeMax=end_time.isoformat(),
                    singleEvents=True,
                    orderBy='startTime',
                    pageToken=page_token,
                    maxResults=250
                ).execute()
                
                events = events_result.get('items', [])
                
                for event in events:
                    # Skip transparent events (marked as "Free")
                    if event.get('transparency') == 'transparent':
                        continue
                    
                    # Check if it's an all-day event
                    is_all_day = 'date' in event.get('start', {})
                    
                    # Skip all-day events if requested
                    if is_all_day and not validated_args.include_all_day:
                        continue
                    
                    # Extract event details
                    event_data = {
                        'id': event.get('id', ''),
                        'title': event.get('summary', 'Untitled Event'),
                        'description': event.get('description', ''),
                        'location': event.get('location', ''),
                        'is_all_day': is_all_day
                    }
                    
                    # Extract start and end times
                    if is_all_day:
                        # All-day event
                        event_data['start_date'] = event['start'].get('date')
                        event_data['end_date'] = event['end'].get('date')
                        event_data['start_time'] = None
                        event_data['end_time'] = None
                    else:
                        # Timed event
                        start_dt = datetime.fromisoformat(event['start'].get('dateTime'))
                        end_dt = datetime.fromisoformat(event['end'].get('dateTime'))
                        event_data['start_time'] = start_dt.isoformat()
                        event_data['end_time'] = end_dt.isoformat()
                        event_data['start_date'] = start_dt.date().isoformat()
                        event_data['end_date'] = end_dt.date().isoformat()
                        event_data['duration_minutes'] = int((end_dt - start_dt).total_seconds() / 60)
                    
                    # Extract attendees
                    attendees = []
                    if 'attendees' in event:
                        for attendee in event['attendees']:
                            attendees.append({
                                'email': attendee.get('email', ''),
                                'display_name': attendee.get('displayName', ''),
                                'response_status': attendee.get('responseStatus', 'needsAction'),
                                'is_organizer': attendee.get('organizer', False)
                            })
                    event_data['attendees'] = attendees
                    event_data['attendee_count'] = len(attendees)
                    
                    # Add recurrence info if available
                    if 'recurringEventId' in event:
                        event_data['is_recurring'] = True
                        event_data['recurring_event_id'] = event['recurringEventId']
                    else:
                        event_data['is_recurring'] = False
                    
                    events_list.append(event_data)
                
                page_token = events_result.get('nextPageToken')
                if not page_token:
                    break
            
            # Sort events by start time
            events_list.sort(key=lambda e: e.get('start_time') or e.get('start_date'))
            
            self.logger.info(f"Successfully retrieved {len(events_list)} events")
            
            # 5. Format the response
            result_data = {
                "message": f"Found {len(events_list)} events in the next {validated_args.days} days.",
                "event_count": len(events_list),
                "events": events_list,
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "timezone": context.preferences.time_zone
                }
            }
            
            return self._create_success_result(result_data)
            
        except Exception as e:
            self.logger.exception(f"Error retrieving calendar events: {e}")
            return self._create_error_result(f"Failed to retrieve calendar events: {str(e)}")


# --- Tool Registry (Conceptual) ---
# The Tool Executor would use a registry like this to find the correct wrapper.
TOOL_REGISTRY: Dict[str, ToolWrapper] = {
    "schedule_activity": ScheduleActivityWrapper(),
    "get_calendar_events": GetCalendarEventsWrapper(),
    # Add other tool wrappers here as they are created
}

# --- Example Usage ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Dummy context objects for example
    class DummyPrefs(UserPreferences):
        user_id: str = Field(..., description="User ID")
        time_zone: str = Field(default="Europe/Paris", description="Time zone")
        working_hours: Dict[DayOfWeek, tuple] = Field(
            default={
                DayOfWeek.MONDAY: (time(9, 0), time(17, 0)),
                DayOfWeek.TUESDAY: (time(9, 0), time(17, 0)),
                DayOfWeek.WEDNESDAY: (time(9, 0), time(17, 0)),
                DayOfWeek.THURSDAY: (time(9, 0), time(17, 0)),
                DayOfWeek.FRIDAY: (time(9, 0), time(16, 0)),
            },
            description="Working hours for each day"
        )
        days_off: List[date] = Field(default=[date(2025, 1, 1)], description="Days off")
        preferred_break_duration: timedelta = Field(
            default=timedelta(minutes=5), description="Preferred break duration"
        )
        work_block_max_duration: timedelta = Field(
            default=timedelta(hours=2), description="Maximum work block duration"
        )
        energy_levels: Dict[tuple, EnergyLevel] = Field(
            default={
                (time(9, 0), time(12, 0)): EnergyLevel.HIGH,
                (time(13, 0), time(17, 0)): EnergyLevel.MEDIUM,
            },
            description="Energy levels throughout the day"
        )
        rest_preferences: Dict[str, tuple] = Field(
            default={"sleep_schedule": (time(23, 59), time(5, 0))},
            description="Rest preferences"
        )

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


    client_secret_path = "../credentials.json"  # Path to your client secret file
    token_path = "../token.json"  # Path to your token file
    scopes = ['https://www.googleapis.com/auth/calendar']  # Define your scopes
    # Attempt to create, might need error handling if creds missing
    client = GoogleCalendarAPIClient(client_secret_path, token_path, scopes)

    exec_context = ExecutionContext(
        user_id="user_123",
        preferences=DummyPrefs(user_id="user_123"),
        calendar_client=client
    )

    # # --- Test Cases ---
    print("\n--- Test Case 1: Flexible Scheduling (Duration) ---")
    args1 = {"title": "Write report", "duration_minutes": 90, "category_str": "WORK", "priority": 8, 'description': "Complete the quarterly report."}
    wrapper1 = ScheduleActivityWrapper()
    result1 = wrapper1.run(args1, exec_context)
    print(result1.model_dump_json(indent=2))

    # print("\n--- Test Case 2: Fixed Time ---")
    # args2 = {"title": "Fixed Meeting", "start_time_str": "2025-05-02T14:00:00+02:00", "end_time_str": "2025-05-02T15:00:00+02:00"
    #          , "description": "Discuss project updates", "category_str": "WORK"}
    # wrapper2 = ScheduleActivityWrapper()
    # result2 = wrapper2.run(args2, exec_context)
    # print(result2.model_dump_json(indent=2))

    # print("\n--- Test Case 3: Insufficient Info ---")
    # args3 = {"title": "Vague Task"}
    # wrapper3 = ScheduleActivityWrapper()
    # result3 = wrapper3.run(args3, exec_context)
    # print(result3.model_dump_json(indent=2))
    #
    # print("\n--- Test Case 4: Validation Error (Bad Category) ---")
    # args4 = {"title": "My Hobby", "duration_minutes": 60, "category_str": "FUN"}
    # wrapper4 = ScheduleActivityWrapper()
    # result4 = wrapper4.run(args4, exec_context)
    # print(result4.model_dump_json(indent=2))
    #
    # print("\n--- Test Case 5: Validation Error (No Title) ---")
    # args5 = {"duration_minutes": 60, "category_str": "WORK"}
    # wrapper5 = ScheduleActivityWrapper()
    # result5 = wrapper5.run(args5, exec_context)
    # print(result5.model_dump_json(indent=2))

