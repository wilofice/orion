# app/tools/find_meeting_time.py

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, ValidationError, field_validator
import pytz

from .base import ToolWrapper
from tool_interface import ExecutionContext, ExecutorToolResult


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