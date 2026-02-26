# app/tools/reschedule_event.py

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError, model_validator
import pytz
from googleapiclient.errors import HttpError

from .base import ToolWrapper, parse_datetime_flexible
from tool_interface import ExecutionContext, ExecutorToolResult


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