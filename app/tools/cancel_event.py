# app/tools/cancel_event.py

import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError
from googleapiclient.errors import HttpError

from .base import ToolWrapper
from tool_interface import ExecutionContext, ExecutorToolResult


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