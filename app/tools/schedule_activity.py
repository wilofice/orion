# app/tools/schedule_activity.py

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator, ValidationError
import pytz

from .base import ToolWrapper, parse_datetime_flexible, parse_timedelta_minutes
from tool_interface import ExecutionContext, ExecutorToolResult
from models import WantToDoActivity, ActivityCategory
from scheduler_logic import schedule_want_to_do_basic


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
            check_start = start_time + timedelta(microseconds=1)
            check_end = end_time - timedelta(microseconds=1)

            if check_start >= check_end:
                 check_start = start_time
                 check_end = end_time

            self.logger.debug(f"Checking for conflicts between {check_start} and {check_end}")
            conflicting_busy_slots = context.calendar_client.get_busy_slots(
                calendar_id='primary',
                start_time=check_start,
                end_time=check_end
            )

            if conflicting_busy_slots:
                conflict_details = ", ".join([f"'{getattr(slot.activity_obj, 'title', 'Unknown Event')}' ({slot.start_time.time()} - {slot.end_time.time()})"
                                            for slot in conflicting_busy_slots if hasattr(slot, 'activity_obj')])
                if not conflict_details: conflict_details = f"{len(conflicting_busy_slots)} existing event(s)"
                error_msg = f"Cannot schedule '{title}' at the requested time because it conflicts with: {conflict_details}."
                self.logger.warning(error_msg)
                return self._create_error_result(error_msg, result_data={"conflicts": [str(s) for s in conflicting_busy_slots]})

            self.logger.info(f"No conflicts found. Adding event '{title}' to calendar.")
            created_event_details = context.calendar_client.add_event(
                title=title,
                start_time=start_time,
                end_time=end_time,
                description=description
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

        try:
            validated_args = ScheduleActivityWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            error_msg = f"Invalid arguments provided for scheduling: {e.errors()}"
            clarification = f"I couldn't understand the details for scheduling. Please clarify: {e.errors()}"
            return self._create_clarification_result(clarification, result_data={"validation_errors": e.errors()})

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
        description: Optional[str] = validated_args.description

        if start_time and end_time:
            if end_time <= start_time:
                return self._create_error_result("End time must be after start time.")
            return self._handle_fixed_time_scheduling(
                title=validated_args.title,
                start_time=start_time,
                end_time=end_time,
                description=description,
                context=context
            )

        elif start_time and duration:
            calculated_end_time = start_time + duration
            return self._handle_fixed_time_scheduling(
                title=validated_args.title,
                start_time=start_time,
                end_time=calculated_end_time,
                description=description,
                context=context
            )

        elif duration:
            estimated_duration = duration
            self.logger.info(f"Scheduling flexible task: duration {duration}")

            if not category:
                return self._create_clarification_result("Please specify a category (e.g., WORK, PERSONAL) for this task.")
            priority = validated_args.priority or 5

            activity_to_schedule = WantToDoActivity(
                title=validated_args.title,
                description=description,
                estimated_duration=estimated_duration,
                priority=priority,
                category=category,
                deadline=deadline,
            )

            try:
                query_start = datetime.now(user_tz)
                query_end = query_start + timedelta(days=7)
                self.logger.info(f"Fetching available slots from {query_start} to {query_end}")
                available_slots = context.calendar_client.get_available_time_slots(
                    calendar_id='primary',
                    preferences=context.preferences,
                    start_time=query_start,
                    end_time=query_end
                )
                self.logger.info(f"Found {len(available_slots)} available slots matching preferences.")

                if not available_slots:
                     return self._create_error_result(f"No available time slots found in the next 7 days matching your preferences.")

                scheduled_map, unscheduled = schedule_want_to_do_basic(
                    want_to_do_list=[activity_to_schedule],
                    available_slots=available_slots
                )

                if activity_to_schedule.id in scheduled_map:
                    scheduled_slot = scheduled_map[activity_to_schedule.id]
                    self.logger.info(f"Successfully scheduled '{activity_to_schedule.title}' at {scheduled_slot.start_time}")

                    created_event_details = context.calendar_client.add_event(
                         title=activity_to_schedule.title,
                         start_time=scheduled_slot.start_time,
                         end_time=scheduled_slot.end_time,
                         description=activity_to_schedule.description
                    )
                    event_id = created_event_details.get("id")
                    event_link = created_event_details.get("htmlLink")
                    event_id = event_id
                    event_link = event_link

                    return self._create_success_result({
                        "message": f"OK. Scheduled '{activity_to_schedule.title}'.",
                        "activity_id": activity_to_schedule.id,
                        "event_id": event_id,
                        "event_link": event_link,
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

        else:
            self.logger.warning("Insufficient information provided for scheduling.")
            return self._create_clarification_result("Please provide at least a duration, or specific start/end times for the activity.")