# app/tools/get_calendar_events.py

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, ValidationError
import pytz

from .base import ToolWrapper
from tool_interface import ExecutionContext, ExecutorToolResult


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
        
        try:
            validated_args = GetCalendarEventsWrapperArgs(**args)
            self.logger.debug("Arguments validated successfully.")
        except ValidationError as e:
            self.logger.error(f"Argument validation failed: {e}")
            error_msg = f"Invalid arguments for retrieving events: {e.errors()}"
            return self._create_error_result(error_msg)
        
        try:
            user_tz = pytz.timezone(context.preferences.time_zone)
        except Exception as e:
            self.logger.error(f"Invalid timezone in user preferences: {context.preferences.time_zone} - {e}")
            return self._create_error_result(f"Invalid timezone configuration: {context.preferences.time_zone}")
        
        now = datetime.now(user_tz)
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(days=validated_args.days)
        
        try:
            self.logger.info(f"Fetching events from {start_time} to {end_time}")
            
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
                
                for event in events:
                    if event.get('transparency') == 'transparent':
                        continue
                    
                    is_all_day = 'date' in event.get('start', {})
                    
                    if is_all_day and not validated_args.include_all_day:
                        continue
                    
                    event_data = {
                        'id': event.get('id', ''),
                        'title': event.get('summary', 'Untitled Event'),
                        'description': event.get('description', ''),
                        'location': event.get('location', ''),
                        'is_all_day': is_all_day
                    }
                    
                    if is_all_day:
                        event_data['start_date'] = event['start'].get('date')
                        event_data['end_date'] = event['end'].get('date')
                        event_data['start_time'] = None
                        event_data['end_time'] = None
                    else:
                        start_dt = datetime.fromisoformat(event['start'].get('dateTime'))
                        end_dt = datetime.fromisoformat(event['end'].get('dateTime'))
                        event_data['start_time'] = start_dt.isoformat()
                        event_data['end_time'] = end_dt.isoformat()
                        event_data['start_date'] = start_dt.date().isoformat()
                        event_data['end_date'] = end_dt.date().isoformat()
                        event_data['duration_minutes'] = int((end_dt - start_dt).total_seconds() / 60)
                    
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
                    
                    if 'recurringEventId' in event:
                        event_data['is_recurring'] = True
                        event_data['recurring_event_id'] = event['recurringEventId']
                    else:
                        event_data['is_recurring'] = False
                    
                    events_list.append(event_data)
                
                page_token = events_result.get('nextPageToken')
                if not page_token:
                    break
            
            events_list.sort(key=lambda e: e.get('start_time') or e.get('start_date'))
            
            self.logger.info(f"Successfully retrieved {len(events_list)} events")
            
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