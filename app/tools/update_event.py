# app/tools/update_event.py

import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, ValidationError, model_validator
from googleapiclient.errors import HttpError

from .base import ToolWrapper
from tool_interface import ExecutionContext, ExecutorToolResult


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