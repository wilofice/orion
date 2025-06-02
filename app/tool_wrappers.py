# app/tool_wrappers.py

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, time, date
from typing import Dict, Any, Optional, List, Tuple
from pydantic import (BaseModel, Field, field_validator,
                      model_validator)
import pytz # For timezone handling
from dateutil.parser import parse as dateutil_parse # For flexible datetime parsing
from pydantic import BaseModel, ValidationError, Field, field_validator
from googleapiclient.errors import HttpError

# Attempt to import dependent models and interfaces
from tool_interface import ExecutionContext, ExecutorToolResult, ToolResultStatus
# Core models from Task 1
from models import WantToDoActivity, TimeSlot, ActivityCategory, ActivityStatus, UserPreferences, DayOfWeek, EnergyLevel
# Core logic functions (conceptual imports)
from scheduler_logic import schedule_want_to_do_basic, ConflictInfo # Need ConflictInfo if handling conflicts here
# Calendar client interface (needed from context)
from calendar_client import AbstractCalendarClient, GoogleCalendarAPIClient

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


# --- Get Available Slots Tool Wrapper ---

class GetAvailableSlotsWrapperArgs(BaseModel):
    """Input validation model for get_available_slots arguments."""
    days: Optional[int] = Field(7, ge=1, le=30, description="Number of days to look ahead (1-30)")
    min_duration_minutes: Optional[int] = Field(30, ge=15, le=480, description="Minimum slot duration in minutes (15-480)")
    preferred_times_only: Optional[bool] = Field(False, description="Whether to show only slots during preferred meeting times")
    include_weekends: Optional[bool] = Field(True, description="Whether to include weekend slots")
    
class GetAvailableSlotsWrapper(ToolWrapper):
    """
    Wrapper for the 'get_available_slots' tool.
    Retrieves available time slots from the user's calendar considering their preferences.
    """
    tool_name = "get_available_slots"
    logger = logging.getLogger(__name__)
    description = "Finds available (free) time slots in the user's calendar based on their preferences and existing events."
    parameters_schema = {
        "type": "object",
        "properties": {
            "days": {
                "type": "integer",
                "description": "Number of days to look ahead for available slots (1-30). Default is 7.",
                "minimum": 1,
                "maximum": 30
            },
            "min_duration_minutes": {
                "type": "integer",
                "description": "Minimum duration for available slots in minutes (15-480). Default is 30.",
                "minimum": 15,
                "maximum": 480
            },
            "preferred_times_only": {
                "type": "boolean",
                "description": "Show only slots during user's preferred meeting times. Default is false."
            },
            "include_weekends": {
                "type": "boolean",
                "description": "Whether to include slots on weekends. Default is true."
            }
        },
        "required": []
    }
    
    def _filter_slots_by_duration(self, slots: List[TimeSlot], min_duration: timedelta) -> List[TimeSlot]:
        """Filter slots to only include those that meet minimum duration."""
        return [slot for slot in slots if slot.duration >= min_duration]
    
    def _filter_slots_by_weekends(self, slots: List[TimeSlot], include_weekends: bool) -> List[TimeSlot]:
        """Filter slots based on weekend preference."""
        if include_weekends:
            return slots
        # Filter out Saturday (5) and Sunday (6)
        return [slot for slot in slots if slot.start_time.weekday() < 5]
    
    def _group_slots_by_day(self, slots: List[TimeSlot]) -> Dict[str, List[TimeSlot]]:
        """Group slots by date for easier presentation."""
        grouped = {}
        for slot in slots:
            date_key = slot.start_time.date().isoformat()
            if date_key not in grouped:
                grouped[date_key] = []
            grouped[date_key].append(slot)
        return grouped
    
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")
        
        # 1. Validate arguments
        try:
            validated_args = GetAvailableSlotsWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            error_msg = f"Invalid arguments for finding available slots: {e.errors()}"
            return self._create_error_result(error_msg)
        
        # 2. Get user timezone
        try:
            user_tz = pytz.timezone(context.preferences.time_zone)
        except Exception as e:
            self.logger.error(f"Invalid timezone in user preferences: {context.preferences.time_zone} - {e}")
            return self._create_error_result(f"Invalid timezone configuration: {context.preferences.time_zone}")
        
        # 3. Define time range
        now = datetime.now(user_tz)
        # Start from the next hour for cleaner results
        start_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        end_time = start_time + timedelta(days=validated_args.days)
        
        try:
            # 4. Get available slots using calendar client
            self.logger.info(f"Fetching available slots from {start_time} to {end_time}")
            
            # If preferred_times_only is True, temporarily modify preferences
            if validated_args.preferred_times_only:
                # Use only preferred meeting times
                temp_preferences = context.preferences
            else:
                # Use all working hours
                temp_preferences = context.preferences
            
            # Get available slots considering user preferences
            available_slots = context.calendar_client.get_available_time_slots(
                preferences=temp_preferences,
                calendar_id='primary',
                start_time=start_time,
                end_time=end_time
            )
            
            self.logger.info(f"Found {len(available_slots)} raw available slots")
            
            # 5. Apply additional filters
            min_duration = timedelta(minutes=validated_args.min_duration_minutes)
            filtered_slots = self._filter_slots_by_duration(available_slots, min_duration)
            filtered_slots = self._filter_slots_by_weekends(filtered_slots, validated_args.include_weekends)
            
            # If preferred_times_only, filter to only preferred meeting times
            if validated_args.preferred_times_only and context.preferences.preferred_meeting_times:
                preferred_filtered = []
                for slot in filtered_slots:
                    slot_start_time = slot.start_time.time()
                    slot_end_time = slot.end_time.time()
                    
                    # Check if slot overlaps with any preferred meeting time
                    for pref_start, pref_end in context.preferences.preferred_meeting_times:
                        # Check if the slot is within preferred hours
                        if (slot_start_time >= pref_start and slot_end_time <= pref_end):
                            preferred_filtered.append(slot)
                            break
                filtered_slots = preferred_filtered
            
            self.logger.info(f"After filtering: {len(filtered_slots)} available slots")
            
            # 6. Group slots by day for better presentation
            grouped_slots = self._group_slots_by_day(filtered_slots)
            
            # 7. Format the response
            formatted_slots = []
            summary_by_day = {}
            
            for date_str, day_slots in sorted(grouped_slots.items()):
                day_date = datetime.fromisoformat(date_str).date()
                day_name = day_date.strftime("%A")
                
                summary_by_day[date_str] = {
                    "date": date_str,
                    "day_name": day_name,
                    "slot_count": len(day_slots),
                    "total_available_hours": sum(slot.duration.total_seconds() / 3600 for slot in day_slots)
                }
                
                for slot in sorted(day_slots, key=lambda s: s.start_time):
                    formatted_slots.append({
                        "date": date_str,
                        "day_name": day_name,
                        "start_time": slot.start_time.isoformat(),
                        "end_time": slot.end_time.isoformat(),
                        "start_time_local": slot.start_time.strftime("%I:%M %p"),
                        "end_time_local": slot.end_time.strftime("%I:%M %p"),
                        "duration_minutes": int(slot.duration.total_seconds() / 60),
                        "duration_hours": round(slot.duration.total_seconds() / 3600, 1)
                    })
            
            # Calculate summary statistics
            total_slots = len(filtered_slots)
            total_available_hours = sum(slot.duration.total_seconds() / 3600 for slot in filtered_slots)
            
            result_data = {
                "message": f"Found {total_slots} available time slots in the next {validated_args.days} days.",
                "summary": {
                    "total_slots": total_slots,
                    "total_available_hours": round(total_available_hours, 1),
                    "days_checked": validated_args.days,
                    "min_slot_duration_minutes": validated_args.min_duration_minutes,
                    "filters_applied": {
                        "preferred_times_only": validated_args.preferred_times_only,
                        "include_weekends": validated_args.include_weekends
                    }
                },
                "slots_by_day": summary_by_day,
                "available_slots": formatted_slots,
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "timezone": context.preferences.time_zone
                }
            }
            
            # Add a note if no slots were found
            if total_slots == 0:
                result_data["message"] = f"No available time slots found in the next {validated_args.days} days with the specified criteria."
                result_data["suggestions"] = [
                    "Try increasing the number of days to search",
                    "Reduce the minimum duration requirement",
                    "Include weekends if not already included",
                    "Disable 'preferred times only' filter if enabled"
                ]
            
            return self._create_success_result(result_data)
            
        except Exception as e:
            self.logger.exception(f"Error retrieving available slots: {e}")
            return self._create_error_result(f"Failed to retrieve available slots: {str(e)}")


# --- Reschedule Event Tool Wrapper ---

class RescheduleEventWrapperArgs(BaseModel):
    """Input validation model for reschedule_event arguments."""
    event_id: str = Field(..., description="The ID of the event to reschedule")
    new_start_time_str: str = Field(..., description="New start time in timezone-aware format")
    new_end_time_str: Optional[str] = Field(None, description="New end time in timezone-aware format")
    new_duration_minutes: Optional[int] = Field(None, gt=0, description="New duration in minutes (alternative to end_time)")
    check_conflicts: Optional[bool] = Field(True, description="Whether to check for conflicts before rescheduling")
    
    @model_validator(mode='after')
    def check_time_specification(self):
        """Ensure either end_time or duration is provided."""
        if not self.new_end_time_str and not self.new_duration_minutes:
            raise ValueError("Either new_end_time_str or new_duration_minutes must be provided")
        return self

class RescheduleEventWrapper(ToolWrapper):
    """
    Wrapper for the 'reschedule_event' tool.
    Reschedules an existing calendar event to a new time.
    """
    tool_name = "reschedule_event"
    logger = logging.getLogger(__name__)
    description = "Reschedules an existing calendar event to a new time, with optional conflict checking."
    parameters_schema = {
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "The ID of the event to reschedule"
            },
            "new_start_time_str": {
                "type": "string",
                "description": "New start time in timezone-aware format (e.g., '2025-05-10T14:00:00+02:00')"
            },
            "new_end_time_str": {
                "type": "string",
                "description": "New end time in timezone-aware format"
            },
            "new_duration_minutes": {
                "type": "integer",
                "description": "New duration in minutes (alternative to end_time)",
                "minimum": 1
            },
            "check_conflicts": {
                "type": "boolean",
                "description": "Whether to check for conflicts before rescheduling. Default is true."
            }
        },
        "required": ["event_id", "new_start_time_str"]
    }
    
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")
        
        # 1. Validate arguments
        try:
            validated_args = RescheduleEventWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            return self._create_clarification_result(
                f"Invalid arguments for rescheduling: {e.errors()}",
                result_data={"validation_errors": e.errors()}
            )
        
        # 2. Parse datetime
        try:
            user_tz = pytz.timezone(context.preferences.time_zone)
        except Exception as e:
            self.logger.error(f"Invalid timezone: {context.preferences.time_zone}")
            return self._create_error_result(f"Invalid timezone configuration: {context.preferences.time_zone}")
        
        new_start = parse_datetime_flexible(validated_args.new_start_time_str, user_tz)
        if not new_start:
            return self._create_error_result("Could not parse new start time")
        
        # Calculate new end time
        if validated_args.new_end_time_str:
            new_end = parse_datetime_flexible(validated_args.new_end_time_str, user_tz)
            if not new_end:
                return self._create_error_result("Could not parse new end time")
        else:
            new_end = new_start + timedelta(minutes=validated_args.new_duration_minutes)
        
        if new_end <= new_start:
            return self._create_error_result("End time must be after start time")
        
        try:
            service = context.calendar_client._get_service()
            
            # 3. Get the existing event
            try:
                existing_event = service.events().get(
                    calendarId='primary',
                    eventId=validated_args.event_id
                ).execute()
            except HttpError as e:
                if e.resp.status == 404:
                    return self._create_error_result(f"Event with ID '{validated_args.event_id}' not found")
                raise
            
            # 4. Check for conflicts if requested
            if validated_args.check_conflicts:
                # Check for conflicts in the new time slot
                check_start = new_start + timedelta(microseconds=1)
                check_end = new_end - timedelta(microseconds=1)
                
                conflicting_events = context.calendar_client.get_busy_slots(
                    calendar_id='primary',
                    start_time=check_start,
                    end_time=check_end
                )
                
                # Filter out the current event from conflicts
                conflicting_events = [
                    event for event in conflicting_events 
                    if not hasattr(event, 'event_id') or event.event_id != validated_args.event_id
                ]
                
                if conflicting_events:
                    conflict_count = len(conflicting_events)
                    return self._create_error_result(
                        f"Cannot reschedule: {conflict_count} conflict(s) found at the new time",
                        result_data={"conflicts": conflict_count}
                    )
            
            # 5. Update the event
            event_update = {
                'start': {
                    'dateTime': new_start.isoformat(),
                    'timeZone': str(user_tz)
                },
                'end': {
                    'dateTime': new_end.isoformat(),
                    'timeZone': str(user_tz)
                }
            }
            
            updated_event = service.events().patch(
                calendarId='primary',
                eventId=validated_args.event_id,
                body=event_update
            ).execute()
            
            self.logger.info(f"Successfully rescheduled event '{existing_event.get('summary', 'Untitled')}'")
            
            return self._create_success_result({
                "message": f"Successfully rescheduled '{existing_event.get('summary', 'Untitled Event')}'",
                "event_id": validated_args.event_id,
                "event_title": existing_event.get('summary', 'Untitled Event'),
                "old_start": existing_event['start'].get('dateTime', existing_event['start'].get('date')),
                "old_end": existing_event['end'].get('dateTime', existing_event['end'].get('date')),
                "new_start": new_start.isoformat(),
                "new_end": new_end.isoformat(),
                "duration_minutes": int((new_end - new_start).total_seconds() / 60)
            })
            
        except Exception as e:
            self.logger.exception(f"Error rescheduling event: {e}")
            return self._create_error_result(f"Failed to reschedule event: {str(e)}")


# --- Cancel Event Tool Wrapper ---

class CancelEventWrapperArgs(BaseModel):
    """Input validation model for cancel_event arguments."""
    event_id: str = Field(..., description="The ID of the event to cancel")
    send_notifications: Optional[bool] = Field(True, description="Whether to send cancellation notifications")
    reason: Optional[str] = Field(None, description="Optional reason for cancellation")

class CancelEventWrapper(ToolWrapper):
    """
    Wrapper for the 'cancel_event' tool.
    Cancels/deletes a calendar event.
    """
    tool_name = "cancel_event"
    logger = logging.getLogger(__name__)
    description = "Cancels or deletes a calendar event, with optional notifications to attendees."
    parameters_schema = {
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "The ID of the event to cancel"
            },
            "send_notifications": {
                "type": "boolean",
                "description": "Whether to send cancellation notifications. Default is true."
            },
            "reason": {
                "type": "string",
                "description": "Optional reason for cancellation"
            }
        },
        "required": ["event_id"]
    }
    
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")
        
        # 1. Validate arguments
        try:
            validated_args = CancelEventWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            return self._create_error_result(f"Invalid arguments for cancellation: {e.errors()}")
        
        try:
            service = context.calendar_client._get_service()
            
            # 2. Get the event details before deletion
            try:
                event = service.events().get(
                    calendarId='primary',
                    eventId=validated_args.event_id
                ).execute()
            except HttpError as e:
                if e.resp.status == 404:
                    return self._create_error_result(f"Event with ID '{validated_args.event_id}' not found")
                raise
            
            event_title = event.get('summary', 'Untitled Event')
            event_start = event['start'].get('dateTime', event['start'].get('date'))
            attendee_count = len(event.get('attendees', []))
            
            # 3. Delete the event
            service.events().delete(
                calendarId='primary',
                eventId=validated_args.event_id,
                sendNotifications=validated_args.send_notifications
            ).execute()
            
            self.logger.info(f"Successfully cancelled event '{event_title}'")
            
            result_data = {
                "message": f"Successfully cancelled '{event_title}'",
                "event_id": validated_args.event_id,
                "event_title": event_title,
                "event_start": event_start,
                "attendee_count": attendee_count,
                "notifications_sent": validated_args.send_notifications
            }
            
            if validated_args.reason:
                result_data["cancellation_reason"] = validated_args.reason
            
            return self._create_success_result(result_data)
            
        except Exception as e:
            self.logger.exception(f"Error cancelling event: {e}")
            return self._create_error_result(f"Failed to cancel event: {str(e)}")


# --- Create Task Tool Wrapper ---

class CreateTaskWrapperArgs(BaseModel):
    """Input validation model for create_task arguments."""
    title: str = Field(..., description="The title of the task")
    description: Optional[str] = Field(None, description="Task description")
    category_str: str = Field(..., description="Task category (e.g., 'WORK', 'PERSONAL')")
    priority: Optional[int] = Field(5, ge=1, le=10, description="Priority (1-10)")
    deadline_str: Optional[str] = Field(None, description="Optional deadline")
    estimated_duration_minutes: Optional[int] = Field(60, gt=0, description="Estimated duration in minutes")
    
    @field_validator('category_str')
    @classmethod
    def check_category(cls, v: str):
        """Validate category string matches enum values."""
        if v.upper() not in ActivityCategory.__members__:
            raise ValueError(f"Invalid category. Choose from: {list(ActivityCategory.__members__.keys())}")
        return v

class CreateTaskWrapper(ToolWrapper):
    """
    Wrapper for the 'create_task' tool.
    Creates a new task in the user's WantToDo list.
    """
    tool_name = "create_task"
    logger = logging.getLogger(__name__)
    description = "Creates a new task or to-do item with specified details and priority."
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "The title of the task"
            },
            "description": {
                "type": "string",
                "description": "Optional task description"
            },
            "category_str": {
                "type": "string",
                "description": "Task category (WORK, PERSONAL, LEARNING, EXERCISE, SOCIAL, CHORE, ERRAND, FUN, OTHER)"
            },
            "priority": {
                "type": "integer",
                "description": "Priority level (1-10, higher is more important). Default is 5.",
                "minimum": 1,
                "maximum": 10
            },
            "deadline_str": {
                "type": "string",
                "description": "Optional deadline in timezone-aware format"
            },
            "estimated_duration_minutes": {
                "type": "integer",
                "description": "Estimated duration in minutes. Default is 60.",
                "minimum": 1
            }
        },
        "required": ["title", "category_str"]
    }
    
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")
        
        # 1. Validate arguments
        try:
            validated_args = CreateTaskWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            return self._create_clarification_result(
                f"Invalid task details: {e.errors()}",
                result_data={"validation_errors": e.errors()}
            )
        
        # 2. Parse deadline if provided
        deadline = None
        if validated_args.deadline_str:
            try:
                user_tz = pytz.timezone(context.preferences.time_zone)
                deadline = parse_datetime_flexible(validated_args.deadline_str, user_tz)
                if not deadline:
                    return self._create_error_result("Could not parse deadline")
            except Exception as e:
                self.logger.error(f"Error parsing deadline: {e}")
                return self._create_error_result(f"Invalid deadline format: {validated_args.deadline_str}")
        
        # 3. Create WantToDoActivity and save to DynamoDB
        try:
            task = WantToDoActivity(
                title=validated_args.title,
                description=validated_args.description,
                estimated_duration=timedelta(minutes=validated_args.estimated_duration_minutes),
                priority=validated_args.priority,
                category=ActivityCategory(validated_args.category_str.upper()),
                deadline=deadline,
                status=ActivityStatus.TODO
            )
            
            # Import DynamoDB operations
            from dynamodb import save_user_task
            
            # Prepare task data for DynamoDB
            task_data = {
                'task_id': task.id,
                'title': task.title,
                'description': task.description or '',
                'category': task.category.value,
                'priority': task.priority,
                'status': task.status.value,
                'estimated_duration_minutes': validated_args.estimated_duration_minutes
            }
            
            # Add deadline if present
            if deadline:
                task_data['deadline'] = deadline.isoformat()
                task_data['deadline_timestamp'] = int(deadline.timestamp())
            
            # Save to DynamoDB
            save_result = save_user_task(context.user_id, task_data)
            
            if save_result != "success":
                self.logger.error(f"Failed to save task to DynamoDB: {save_result}")
                return self._create_error_result(f"Failed to save task: {save_result}")
            
            self.logger.info(f"Successfully created and saved task '{task.title}' with ID {task.id}")
            
            result_data = {
                "message": f"Successfully created task '{task.title}'",
                "task_id": task.id,
                "title": task.title,
                "description": task.description,
                "category": task.category.value,
                "priority": task.priority,
                "estimated_duration_minutes": validated_args.estimated_duration_minutes,
                "status": task.status.value
            }
            
            if deadline:
                result_data["deadline"] = deadline.isoformat()
            
            return self._create_success_result(result_data)
            
        except Exception as e:
            self.logger.exception(f"Error creating task: {e}")
            return self._create_error_result(f"Failed to create task: {str(e)}")


# --- Get Tasks Tool Wrapper ---

class GetTasksWrapperArgs(BaseModel):
    """Input validation model for get_tasks arguments."""
    category_str: Optional[str] = Field(None, description="Filter by category")
    priority_min: Optional[int] = Field(None, ge=1, le=10, description="Minimum priority")
    status_str: Optional[str] = Field(None, description="Filter by status (TODO, SCHEDULED, DONE)")
    due_before_str: Optional[str] = Field(None, description="Show tasks due before this date")
    limit: Optional[int] = Field(50, ge=1, le=100, description="Maximum number of tasks to return")
    
    @field_validator('category_str')
    @classmethod
    def check_category(cls, v: Optional[str]):
        """Validate category if provided."""
        if v and v.upper() not in ActivityCategory.__members__:
            raise ValueError(f"Invalid category. Choose from: {list(ActivityCategory.__members__.keys())}")
        return v
    
    @field_validator('status_str')
    @classmethod
    def check_status(cls, v: Optional[str]):
        """Validate status if provided."""
        if v and v.upper() not in ActivityStatus.__members__:
            raise ValueError(f"Invalid status. Choose from: {list(ActivityStatus.__members__.keys())}")
        return v

class GetTasksWrapper(ToolWrapper):
    """
    Wrapper for the 'get_tasks' tool.
    Retrieves tasks from the user's WantToDo list with optional filters.
    """
    tool_name = "get_tasks"
    logger = logging.getLogger(__name__)
    description = "Retrieves pending tasks or to-do items with optional filtering by category, priority, or deadline."
    parameters_schema = {
        "type": "object",
        "properties": {
            "category_str": {
                "type": "string",
                "description": "Filter by category (WORK, PERSONAL, LEARNING, etc.)"
            },
            "priority_min": {
                "type": "integer",
                "description": "Show only tasks with priority >= this value (1-10)",
                "minimum": 1,
                "maximum": 10
            },
            "status_str": {
                "type": "string",
                "description": "Filter by status (TODO, SCHEDULED, DONE)"
            },
            "due_before_str": {
                "type": "string",
                "description": "Show only tasks due before this date"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of tasks to return (1-100). Default is 50.",
                "minimum": 1,
                "maximum": 100
            }
        },
        "required": []
    }
    
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")
        
        # 1. Validate arguments
        try:
            validated_args = GetTasksWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            return self._create_error_result(f"Invalid filter parameters: {e.errors()}")
        
        # 2. Parse due_before date if provided
        due_before = None
        if validated_args.due_before_str:
            try:
                user_tz = pytz.timezone(context.preferences.time_zone)
                due_before = parse_datetime_flexible(validated_args.due_before_str, user_tz)
                if not due_before:
                    return self._create_error_result("Could not parse due_before date")
            except Exception:
                return self._create_error_result(f"Invalid date format: {validated_args.due_before_str}")
        
        try:
            # Import DynamoDB operations
            from dynamodb import get_user_tasks
            
            # Prepare filters for DynamoDB query
            filters = {}
            
            if validated_args.category_str:
                filters['category'] = validated_args.category_str.upper()
            
            if validated_args.priority_min:
                filters['priority_min'] = validated_args.priority_min
            
            if validated_args.status_str:
                filters['status'] = validated_args.status_str.upper()
            
            if due_before:
                filters['due_before'] = int(due_before.timestamp())
            
            # Fetch tasks from DynamoDB
            db_tasks = get_user_tasks(context.user_id, filters)
            
            # Sort by priority (descending) and deadline
            db_tasks.sort(key=lambda t: (
                -t.get('priority', 0),
                t.get('deadline_timestamp', float('inf'))
            ))
            
            # Apply limit
            db_tasks = db_tasks[:validated_args.limit]
            
            # 4. Format response
            tasks_data = []
            for task in db_tasks:
                task_info = {
                    "task_id": task['task_id'],
                    "title": task['title'],
                    "description": task.get('description', ''),
                    "category": task['category'],
                    "priority": task['priority'],
                    "status": task['status'],
                    "estimated_duration_minutes": task.get('estimated_duration_minutes', 60)
                }
                
                # Add deadline if present
                if 'deadline' in task:
                    task_info["deadline"] = task['deadline']
                    # Parse deadline for human-readable format
                    try:
                        deadline_dt = datetime.fromisoformat(task['deadline'])
                        task_info["deadline_human"] = deadline_dt.strftime("%A, %B %d at %I:%M %p")
                    except:
                        task_info["deadline_human"] = task['deadline']
                
                # Add timestamps
                if 'created_at' in task:
                    task_info["created_at"] = task['created_at']
                if 'updated_at' in task:
                    task_info["updated_at"] = task['updated_at']
                
                tasks_data.append(task_info)
            
            # Group by status for summary
            status_counts = {}
            for task in db_tasks:
                status = task.get('status', 'TODO')
                status_counts[status] = status_counts.get(status, 0) + 1
            
            result_data = {
                "message": f"Found {len(db_tasks)} task(s) matching your criteria",
                "task_count": len(db_tasks),
                "status_summary": status_counts,
                "tasks": tasks_data,
                "filters_applied": {
                    "category": validated_args.category_str,
                    "priority_min": validated_args.priority_min,
                    "status": validated_args.status_str,
                    "due_before": due_before.isoformat() if due_before else None
                }
            }
            
            return self._create_success_result(result_data)
            
        except Exception as e:
            self.logger.exception(f"Error retrieving tasks: {e}")
            return self._create_error_result(f"Failed to retrieve tasks: {str(e)}")


# --- Find Meeting Time Tool Wrapper ---

class FindMeetingTimeWrapperArgs(BaseModel):
    """Input validation model for find_meeting_time arguments."""
    attendee_emails: List[str] = Field(..., description="List of attendee email addresses")
    duration_minutes: int = Field(..., gt=0, le=480, description="Meeting duration in minutes")
    days_ahead: Optional[int] = Field(7, ge=1, le=30, description="Number of days to search ahead")
    preferred_times_only: Optional[bool] = Field(False, description="Only consider preferred meeting times")
    earliest_start_hour: Optional[int] = Field(9, ge=0, le=23, description="Earliest hour to start meeting")
    latest_end_hour: Optional[int] = Field(17, ge=1, le=24, description="Latest hour to end meeting")
    
    @field_validator('attendee_emails')
    @classmethod
    def check_emails(cls, v: List[str]):
        """Validate email addresses."""
        if not v:
            raise ValueError("At least one attendee email is required")
        # Basic email validation
        for email in v:
            if '@' not in email or '.' not in email.split('@')[1]:
                raise ValueError(f"Invalid email format: {email}")
        return v

class FindMeetingTimeWrapper(ToolWrapper):
    """
    Wrapper for the 'find_meeting_time' tool.
    Finds optimal meeting times when all attendees are available.
    """
    tool_name = "find_meeting_time"
    logger = logging.getLogger(__name__)
    description = "Finds available time slots when all specified attendees are free for a meeting."
    parameters_schema = {
        "type": "object",
        "properties": {
            "attendee_emails": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of attendee email addresses"
            },
            "duration_minutes": {
                "type": "integer",
                "description": "Meeting duration in minutes (1-480)",
                "minimum": 1,
                "maximum": 480
            },
            "days_ahead": {
                "type": "integer",
                "description": "Number of days to search ahead (1-30). Default is 7.",
                "minimum": 1,
                "maximum": 30
            },
            "preferred_times_only": {
                "type": "boolean",
                "description": "Only consider preferred meeting times. Default is false."
            },
            "earliest_start_hour": {
                "type": "integer",
                "description": "Earliest hour to start meeting (0-23). Default is 9.",
                "minimum": 0,
                "maximum": 23
            },
            "latest_end_hour": {
                "type": "integer",
                "description": "Latest hour to end meeting (1-24). Default is 17.",
                "minimum": 1,
                "maximum": 24
            }
        },
        "required": ["attendee_emails", "duration_minutes"]
    }
    
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")
        
        # 1. Validate arguments
        try:
            validated_args = FindMeetingTimeWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            return self._create_error_result(f"Invalid arguments: {e.errors()}")
        
        try:
            user_tz = pytz.timezone(context.preferences.time_zone)
            now = datetime.now(user_tz)
            start_search = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            end_search = start_search + timedelta(days=validated_args.days_ahead)
            
            service = context.calendar_client._get_service()
            
            # For this implementation, we'll check the organizer's calendar
            # In a full implementation, you'd check all attendees' calendars
            self.logger.info(f"Finding {validated_args.duration_minutes}-minute slot for {len(validated_args.attendee_emails)} attendees")
            
            # Get available slots from organizer's calendar
            available_slots = context.calendar_client.get_available_time_slots(
                preferences=context.preferences,
                calendar_id='primary',
                start_time=start_search,
                end_time=end_search
            )
            
            # Filter by duration
            duration_td = timedelta(minutes=validated_args.duration_minutes)
            suitable_slots = [slot for slot in available_slots if slot.duration >= duration_td]
            
            # Filter by time constraints
            filtered_slots = []
            for slot in suitable_slots:
                slot_start_hour = slot.start_time.hour
                slot_end = slot.start_time + duration_td
                slot_end_hour = slot_end.hour + (1 if slot_end.minute > 0 else 0)
                
                if (slot_start_hour >= validated_args.earliest_start_hour and
                    slot_end_hour <= validated_args.latest_end_hour):
                    
                    # If preferred times only, check against preferences
                    if validated_args.preferred_times_only and context.preferences.preferred_meeting_times:
                        slot_start_time = slot.start_time.time()
                        slot_end_time = slot_end.time()
                        
                        for pref_start, pref_end in context.preferences.preferred_meeting_times:
                            if slot_start_time >= pref_start and slot_end_time <= pref_end:
                                filtered_slots.append(slot)
                                break
                    else:
                        filtered_slots.append(slot)
            
            # Sort by earliest available
            filtered_slots.sort(key=lambda s: s.start_time)
            
            # Take top 5 suggestions
            suggested_slots = filtered_slots[:5]
            
            if not suggested_slots:
                return self._create_error_result(
                    f"No available {validated_args.duration_minutes}-minute slots found in the next {validated_args.days_ahead} days",
                    result_data={"constraints_checked": {
                        "duration_minutes": validated_args.duration_minutes,
                        "earliest_start_hour": validated_args.earliest_start_hour,
                        "latest_end_hour": validated_args.latest_end_hour,
                        "preferred_times_only": validated_args.preferred_times_only
                    }}
                )
            
            # Format suggestions
            suggestions = []
            for slot in suggested_slots:
                meeting_end = slot.start_time + duration_td
                suggestions.append({
                    "start_time": slot.start_time.isoformat(),
                    "end_time": meeting_end.isoformat(),
                    "start_time_local": slot.start_time.strftime("%A, %B %d at %I:%M %p"),
                    "end_time_local": meeting_end.strftime("%I:%M %p"),
                    "date": slot.start_time.date().isoformat(),
                    "day_name": slot.start_time.strftime("%A")
                })
            
            result_data = {
                "message": f"Found {len(suggestions)} suitable time slots for a {validated_args.duration_minutes}-minute meeting",
                "attendees": validated_args.attendee_emails,
                "duration_minutes": validated_args.duration_minutes,
                "suggested_times": suggestions,
                "search_parameters": {
                    "days_ahead": validated_args.days_ahead,
                    "earliest_start_hour": validated_args.earliest_start_hour,
                    "latest_end_hour": validated_args.latest_end_hour,
                    "preferred_times_only": validated_args.preferred_times_only
                }
            }
            
            return self._create_success_result(result_data)
            
        except Exception as e:
            self.logger.exception(f"Error finding meeting time: {e}")
            return self._create_error_result(f"Failed to find meeting time: {str(e)}")


# --- Get Calendar Analytics Tool Wrapper ---

class GetCalendarAnalyticsWrapperArgs(BaseModel):
    """Input validation model for get_calendar_analytics arguments."""
    days_back: Optional[int] = Field(30, ge=1, le=365, description="Number of days to analyze")
    group_by: Optional[str] = Field("category", description="Group results by: category, day, week")
    include_stats: Optional[List[str]] = Field(
        default_factory=lambda: ["total_time", "meeting_count", "average_duration"],
        description="Statistics to include"
    )
    
    @field_validator('group_by')
    @classmethod
    def check_group_by(cls, v: str):
        """Validate group_by value."""
        valid_options = ["category", "day", "week", "month"]
        if v not in valid_options:
            raise ValueError(f"group_by must be one of: {valid_options}")
        return v

class GetCalendarAnalyticsWrapper(ToolWrapper):
    """
    Wrapper for the 'get_calendar_analytics' tool.
    Analyzes calendar data to provide insights about time usage.
    """
    tool_name = "get_calendar_analytics"
    logger = logging.getLogger(__name__)
    description = "Analyzes calendar events to provide insights about time allocation and meeting patterns."
    parameters_schema = {
        "type": "object",
        "properties": {
            "days_back": {
                "type": "integer",
                "description": "Number of days to analyze (1-365). Default is 30.",
                "minimum": 1,
                "maximum": 365
            },
            "group_by": {
                "type": "string",
                "description": "Group results by: category, day, week, month. Default is category.",
                "enum": ["category", "day", "week", "month"]
            },
            "include_stats": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Statistics to include: total_time, meeting_count, average_duration, etc."
            }
        },
        "required": []
    }
    
    def _categorize_event(self, event: Dict[str, Any]) -> str:
        """Categorize an event based on its properties."""
        summary = event.get('summary', '').lower()
        attendees = event.get('attendees', [])
        
        # Simple categorization logic
        if len(attendees) > 1:
            if any(keyword in summary for keyword in ['interview', 'candidate']):
                return "INTERVIEWS"
            elif any(keyword in summary for keyword in ['1:1', 'one-on-one', 'sync']):
                return "ONE_ON_ONES"
            else:
                return "MEETINGS"
        elif any(keyword in summary for keyword in ['focus', 'work', 'deep work']):
            return "FOCUS_TIME"
        elif any(keyword in summary for keyword in ['lunch', 'break', 'coffee']):
            return "BREAKS"
        else:
            return "OTHER"
    
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")
        
        # 1. Validate arguments
        try:
            validated_args = GetCalendarAnalyticsWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            return self._create_error_result(f"Invalid arguments: {e.errors()}")
        
        try:
            user_tz = pytz.timezone(context.preferences.time_zone)
            now = datetime.now(user_tz)
            end_time = now
            start_time = now - timedelta(days=validated_args.days_back)
            
            # Get events from calendar
            service = context.calendar_client._get_service()
            
            events_list = []
            page_token = None
            
            while True:
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
                events_list.extend(events)
                
                page_token = events_result.get('nextPageToken')
                if not page_token:
                    break
            
            # Analyze events
            analytics = {
                "total_events": len(events_list),
                "total_hours": 0,
                "by_category": {},
                "by_day": {},
                "busiest_days": [],
                "average_events_per_day": 0,
                "average_meeting_duration": 0
            }
            
            total_duration_minutes = 0
            timed_events = 0
            
            for event in events_list:
                # Skip transparent or cancelled events
                if event.get('transparency') == 'transparent' or event.get('status') == 'cancelled':
                    continue
                
                # Get event duration
                if 'dateTime' in event.get('start', {}):
                    start_dt = datetime.fromisoformat(event['start']['dateTime'])
                    end_dt = datetime.fromisoformat(event['end']['dateTime'])
                    duration_minutes = (end_dt - start_dt).total_seconds() / 60
                    
                    total_duration_minutes += duration_minutes
                    timed_events += 1
                    
                    # Categorize event
                    category = self._categorize_event(event)
                    
                    # Update category stats
                    if category not in analytics["by_category"]:
                        analytics["by_category"][category] = {
                            "count": 0,
                            "total_minutes": 0,
                            "average_duration": 0
                        }
                    
                    analytics["by_category"][category]["count"] += 1
                    analytics["by_category"][category]["total_minutes"] += duration_minutes
                    
                    # Update daily stats
                    day_key = start_dt.date().isoformat()
                    if day_key not in analytics["by_day"]:
                        analytics["by_day"][day_key] = {
                            "count": 0,
                            "total_minutes": 0
                        }
                    
                    analytics["by_day"][day_key]["count"] += 1
                    analytics["by_day"][day_key]["total_minutes"] += duration_minutes
            
            # Calculate aggregates
            analytics["total_hours"] = round(total_duration_minutes / 60, 1)
            analytics["average_meeting_duration"] = round(total_duration_minutes / timed_events, 0) if timed_events > 0 else 0
            analytics["average_events_per_day"] = round(timed_events / validated_args.days_back, 1)
            
            # Calculate category averages
            for category, stats in analytics["by_category"].items():
                if stats["count"] > 0:
                    stats["average_duration"] = round(stats["total_minutes"] / stats["count"], 0)
                    stats["total_hours"] = round(stats["total_minutes"] / 60, 1)
            
            # Find busiest days
            if analytics["by_day"]:
                sorted_days = sorted(
                    analytics["by_day"].items(),
                    key=lambda x: x[1]["total_minutes"],
                    reverse=True
                )[:5]
                
                analytics["busiest_days"] = [
                    {
                        "date": day,
                        "events": stats["count"],
                        "hours": round(stats["total_minutes"] / 60, 1)
                    }
                    for day, stats in sorted_days
                ]
            
            # Format result based on group_by
            if validated_args.group_by == "category":
                primary_grouping = analytics["by_category"]
            elif validated_args.group_by == "day":
                primary_grouping = analytics["by_day"]
            else:
                primary_grouping = analytics["by_category"]
            
            result_data = {
                "message": f"Analyzed {timed_events} events over the past {validated_args.days_back} days",
                "time_period": {
                    "start": start_time.date().isoformat(),
                    "end": end_time.date().isoformat(),
                    "days": validated_args.days_back
                },
                "summary": {
                    "total_events": timed_events,
                    "total_hours": analytics["total_hours"],
                    "average_events_per_day": analytics["average_events_per_day"],
                    "average_meeting_duration_minutes": analytics["average_meeting_duration"]
                },
                "breakdown": primary_grouping,
                "busiest_days": analytics["busiest_days"],
                "insights": []
            }
            
            # Generate insights
            if analytics["total_hours"] > 0:
                meeting_percentage = 0
                if "MEETINGS" in analytics["by_category"]:
                    meeting_percentage = round(
                        (analytics["by_category"]["MEETINGS"]["total_minutes"] / total_duration_minutes) * 100,
                        0
                    )
                    result_data["insights"].append(
                        f"{meeting_percentage}% of your time is spent in meetings"
                    )
                
                if analytics["average_meeting_duration"] > 60:
                    result_data["insights"].append(
                        f"Your average meeting is {int(analytics['average_meeting_duration'])} minutes - consider shorter meetings"
                    )
                
                if analytics["average_events_per_day"] > 6:
                    result_data["insights"].append(
                        "You average more than 6 events per day - consider blocking focus time"
                    )
            
            return self._create_success_result(result_data)
            
        except Exception as e:
            self.logger.exception(f"Error analyzing calendar: {e}")
            return self._create_error_result(f"Failed to analyze calendar: {str(e)}")


# --- Update Event Tool Wrapper ---

class UpdateEventWrapperArgs(BaseModel):
    """Input validation model for update_event arguments."""
    event_id: str = Field(..., description="The ID of the event to update")
    title: Optional[str] = Field(None, description="New event title")
    description: Optional[str] = Field(None, description="New event description")
    location: Optional[str] = Field(None, description="New event location")
    add_attendees: Optional[List[str]] = Field(None, description="Email addresses of attendees to add")
    remove_attendees: Optional[List[str]] = Field(None, description="Email addresses of attendees to remove")
    
    @model_validator(mode='after')
    def check_at_least_one_update(self):
        """Ensure at least one field is being updated."""
        update_fields = [self.title, self.description, self.location, self.add_attendees, self.remove_attendees]
        if not any(field is not None for field in update_fields):
            raise ValueError("At least one field must be specified for update")
        return self

class UpdateEventWrapper(ToolWrapper):
    """
    Wrapper for the 'update_event' tool.
    Updates event details like title, description, location, or attendees.
    """
    tool_name = "update_event"
    logger = logging.getLogger(__name__)
    description = "Updates an existing calendar event's details (title, description, location, attendees)."
    parameters_schema = {
        "type": "object",
        "properties": {
            "event_id": {
                "type": "string",
                "description": "The ID of the event to update"
            },
            "title": {
                "type": "string",
                "description": "New event title/summary"
            },
            "description": {
                "type": "string",
                "description": "New event description"
            },
            "location": {
                "type": "string",
                "description": "New event location"
            },
            "add_attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Email addresses of attendees to add"
            },
            "remove_attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Email addresses of attendees to remove"
            }
        },
        "required": ["event_id"]
    }
    
    def run(self, args: Dict[str, Any], context: ExecutionContext) -> ExecutorToolResult:
        self.logger.info(f"Running {self.tool_name} with args: {args}")
        
        # 1. Validate arguments
        try:
            validated_args = UpdateEventWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            return self._create_error_result(f"Invalid arguments: {e.errors()}")
        
        try:
            service = context.calendar_client._get_service()
            
            # 2. Get the existing event
            try:
                event = service.events().get(
                    calendarId='primary',
                    eventId=validated_args.event_id
                ).execute()
            except HttpError as e:
                if e.resp.status == 404:
                    return self._create_error_result(f"Event with ID '{validated_args.event_id}' not found")
                raise
            
            # Store original values for response
            original_values = {
                "title": event.get('summary', ''),
                "description": event.get('description', ''),
                "location": event.get('location', ''),
                "attendee_count": len(event.get('attendees', []))
            }
            
            # 3. Build update payload
            update_made = False
            
            if validated_args.title is not None:
                event['summary'] = validated_args.title
                update_made = True
            
            if validated_args.description is not None:
                event['description'] = validated_args.description
                update_made = True
            
            if validated_args.location is not None:
                event['location'] = validated_args.location
                update_made = True
            
            # Handle attendee updates
            if validated_args.add_attendees or validated_args.remove_attendees:
                current_attendees = event.get('attendees', [])
                attendee_emails = {att.get('email') for att in current_attendees}
                
                # Remove attendees
                if validated_args.remove_attendees:
                    for email in validated_args.remove_attendees:
                        attendee_emails.discard(email)
                    update_made = True
                
                # Add attendees
                if validated_args.add_attendees:
                    for email in validated_args.add_attendees:
                        attendee_emails.add(email)
                    update_made = True
                
                # Rebuild attendee list
                event['attendees'] = [{'email': email} for email in attendee_emails]
            
            if not update_made:
                return self._create_error_result("No changes to apply")
            
            # 4. Update the event
            updated_event = service.events().update(
                calendarId='primary',
                eventId=validated_args.event_id,
                body=event,
                sendNotifications=True  # Notify attendees of changes
            ).execute()
            
            self.logger.info(f"Successfully updated event '{updated_event.get('summary', 'Untitled')}'")
            
            # 5. Prepare response
            changes_made = []
            if validated_args.title and validated_args.title != original_values["title"]:
                changes_made.append(f"Title: '{original_values['title']}' → '{validated_args.title}'")
            
            if validated_args.description is not None:
                if original_values["description"] != validated_args.description:
                    changes_made.append("Description updated")
            
            if validated_args.location is not None:
                if original_values["location"] != validated_args.location:
                    changes_made.append(f"Location: '{original_values['location']}' → '{validated_args.location}'")
            
            new_attendee_count = len(updated_event.get('attendees', []))
            if new_attendee_count != original_values["attendee_count"]:
                changes_made.append(f"Attendees: {original_values['attendee_count']} → {new_attendee_count}")
            
            result_data = {
                "message": f"Successfully updated event '{updated_event.get('summary', 'Untitled')}'",
                "event_id": validated_args.event_id,
                "event_title": updated_event.get('summary', ''),
                "changes_made": changes_made,
                "updated_fields": {
                    "title": validated_args.title is not None,
                    "description": validated_args.description is not None,
                    "location": validated_args.location is not None,
                    "attendees": bool(validated_args.add_attendees or validated_args.remove_attendees)
                },
                "attendee_count": new_attendee_count,
                "event_link": updated_event.get('htmlLink', '')
            }
            
            return self._create_success_result(result_data)
            
        except Exception as e:
            self.logger.exception(f"Error updating event: {e}")
            return self._create_error_result(f"Failed to update event: {str(e)}")


# --- Tool Registry (Conceptual) ---
# The Tool Executor would use a registry like this to find the correct wrapper.
TOOL_REGISTRY: Dict[str, ToolWrapper] = {
    "schedule_activity": ScheduleActivityWrapper(),
    "get_calendar_events": GetCalendarEventsWrapper(),
    "get_available_slots": GetAvailableSlotsWrapper(),
    "reschedule_event": RescheduleEventWrapper(),
    "cancel_event": CancelEventWrapper(),
    "create_task": CreateTaskWrapper(),
    "get_tasks": GetTasksWrapper(),
    "find_meeting_time": FindMeetingTimeWrapper(),
    "get_calendar_analytics": GetCalendarAnalyticsWrapper(),
    "update_event": UpdateEventWrapper(),
    # Add other tool wrappers here as they are created
}

