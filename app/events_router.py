import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from calendar_client import GoogleCalendarAPIClient
from db import get_decrypted_user_tokens
from models import TimeSlot
from zoneinfo import ZoneInfo
from core.security import verify_token

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize an APIRouter instance for event-related routes
router = APIRouter(
    prefix="/events",
    tags=["Events"],
)


# --- Response Models ---
class CalendarEvent(BaseModel):
    """Represents a calendar event."""
    id: str = Field(..., description="Unique identifier for the event")
    title: str = Field(..., description="Event title/summary")
    start_time: datetime = Field(..., description="Event start time (timezone-aware)")
    end_time: datetime = Field(..., description="Event end time (timezone-aware)")
    description: str = Field(default="", description="Event description")
    location: str = Field(default="", description="Event location")
    attendees: List[str] = Field(default_factory=list, description="List of attendee emails")
    is_all_day: bool = Field(default=False, description="Whether this is an all-day event")


class EventsResponse(BaseModel):
    """Response model for events endpoint."""
    user_id: str = Field(..., description="User ID for which events were fetched")
    events: List[CalendarEvent] = Field(..., description="List of calendar events")
    time_range: Dict[str, datetime] = Field(..., description="Time range for the query")
    total_events: int = Field(..., description="Total number of events found")


# --- Helper Functions ---
async def get_calendar_client_for_user(user_id: str) -> GoogleCalendarAPIClient:
    """
    Creates a Google Calendar client for a specific user.
    
    Args:
        user_id: The user ID to get calendar client for
        
    Returns:
        GoogleCalendarAPIClient instance
        
    Raises:
        HTTPException: If user tokens are not found or invalid
    """
    # Get user tokens from DynamoDB
    tokens = get_decrypted_user_tokens(user_id)
    
    if not tokens or 'access_token' not in tokens:
        logger.error(f"No valid tokens found for user {user_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User tokens not found or invalid. Please reconnect Google Calendar."
        )
    
    # Create calendar client with the user's tokens
    try:
        client = GoogleCalendarAPIClient(token_info=tokens)
        return client
    except Exception as e:
        logger.error(f"Failed to create calendar client for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize calendar client"
        )


def convert_timeslot_to_event(slot: TimeSlot, event_data: Dict[str, Any]) -> CalendarEvent:
    """
    Converts a TimeSlot and Google Calendar event data to CalendarEvent model.
    
    Args:
        slot: TimeSlot object with start and end times
        event_data: Raw event data from Google Calendar API
        
    Returns:
        CalendarEvent model instance
    """
    # Extract attendee emails
    attendees = []
    if 'attendees' in event_data:
        attendees = [attendee.get('email', '') for attendee in event_data['attendees'] if attendee.get('email')]
    
    # Check if it's an all-day event
    is_all_day = 'date' in event_data.get('start', {})
    
    return CalendarEvent(
        id=event_data.get('id', ''),
        title=event_data.get('summary', 'Untitled Event'),
        start_time=slot.start_time,
        end_time=slot.end_time,
        description=event_data.get('description', ''),
        location=event_data.get('location', ''),
        attendees=attendees,
        is_all_day=is_all_day
    )


# --- API Endpoints ---
@router.get("/{user_id}/upcoming", response_model=EventsResponse)
async def get_upcoming_events(
    user_id: str,
    days: int = 7,
    timezone: str = "UTC",
    current_user_id: str = Depends(verify_token)
) -> EventsResponse:
    """
    Retrieve upcoming events for a user from their Google Calendar.
    
    Args:
        user_id: The ID of the user to fetch events for
        days: Number of days to look ahead (default: 7)
        timezone: Timezone for the query (default: UTC)
        
    Returns:
        EventsResponse with list of upcoming events
        
    Raises:
        HTTPException: If authentication fails or calendar access errors occur
    """
    logger.info(f"Fetching upcoming events for user {user_id} for next {days} days in timezone {timezone}")
    
    # Verify that the authenticated user can only access their own events
    if current_user_id != user_id:
        logger.warning(f"User {current_user_id} attempted to access events for user {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own calendar events"
        )
    
    # Validate days parameter
    if days < 1 or days > 30:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Days parameter must be between 1 and 30"
        )
    
    # Validate timezone
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timezone: {timezone}"
        )
    
    # Get calendar client for the user
    calendar_client = await get_calendar_client_for_user(user_id)
    
    # Define time range
    now = datetime.now(tz)
    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(days=days)
    
    try:
        # Get busy slots (which represent the user's events)
        # Note: We need to modify this to also get event details
        service = calendar_client._get_service()

        events_list = []
        page_token = None
        
        while True:
            # Call the Google Calendar API directly to get full event details
            data = service.events()
            events_result = data.list(
                calendarId='primary',
                timeMin=start_time.isoformat(),
                timeMax=end_time.isoformat(),
                singleEvents=True,
                orderBy='startTime',
                pageToken=page_token,
                maxResults=250  # Reasonable limit per page
            ).execute()
            
            events = events_result.get('items', [])
            
            for event in events:
                # Skip transparent events (marked as "Free")
                if event.get('transparency') == 'transparent':
                    continue
                
                # Extract start and end times
                start_str = event['start'].get('dateTime', event['start'].get('date'))
                end_str = event['end'].get('dateTime', event['end'].get('date'))
                
                # Handle all-day events vs timed events
                if 'dateTime' in event['start']:
                    # Timed event
                    event_start = datetime.fromisoformat(start_str)
                    event_end = datetime.fromisoformat(end_str)
                else:
                    # All-day event
                    from datetime import date, time
                    event_date = date.fromisoformat(start_str)
                    event_start = datetime.combine(event_date, time.min, tzinfo=tz)
                    event_end_date = date.fromisoformat(end_str)
                    event_end = datetime.combine(event_end_date, time.min, tzinfo=tz)
                
                # Create TimeSlot for the event
                if event_end > event_start:
                    slot = TimeSlot(start_time=event_start, end_time=event_end)
                    calendar_event = convert_timeslot_to_event(slot, event)
                    events_list.append(calendar_event)
            
            page_token = events_result.get('nextPageToken')
            if not page_token:
                break
        
        # Sort events by start time
        events_list.sort(key=lambda e: e.start_time)
        
        logger.info(f"Successfully fetched {len(events_list)} events for user {user_id}")
        
        return EventsResponse(
            user_id=user_id,
            events=events_list,
            time_range={
                "start": start_time,
                "end": end_time
            },
            total_events=len(events_list)
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error fetching events for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch calendar events: {str(e)}"
        )


@router.get("/{user_id}/busy-slots", response_model=Dict[str, Any])
async def get_busy_slots(
    user_id: str,
    days: int = 7,
    timezone: str = "UTC",
    current_user_id: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Retrieve busy time slots for a user from their Google Calendar.
    This endpoint returns TimeSlot objects representing when the user is busy.
    
    Args:
        user_id: The ID of the user to fetch busy slots for
        days: Number of days to look ahead (default: 7)
        timezone: Timezone for the query (default: UTC)
        
    Returns:
        Dictionary with busy slots information
        
    Raises:
        HTTPException: If authentication fails or calendar access errors occur
    """
    logger.info(f"Fetching busy slots for user {user_id} for next {days} days in timezone {timezone}")
    
    # Verify that the authenticated user can only access their own busy slots
    if current_user_id != user_id:
        logger.warning(f"User {current_user_id} attempted to access busy slots for user {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own calendar busy slots"
        )
    
    # Validate parameters
    if days < 1 or days > 30:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Days parameter must be between 1 and 30"
        )
    
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid timezone: {timezone}"
        )
    
    # Get calendar client
    calendar_client = await get_calendar_client_for_user(user_id)
    
    # Define time range
    now = datetime.now(tz)
    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(days=days)
    
    try:
        # Get busy slots using the calendar client
        busy_slots = calendar_client.get_busy_slots(
            calendar_id='primary',
            start_time=start_time,
            end_time=end_time
        )
        
        # Convert TimeSlot objects to dictionaries for JSON response
        busy_slots_data = [
            {
                "start_time": slot.start_time.isoformat(),
                "end_time": slot.end_time.isoformat(),
                "duration_minutes": int(slot.duration.total_seconds() / 60)
            }
            for slot in busy_slots
        ]
        
        logger.info(f"Successfully fetched {len(busy_slots)} busy slots for user {user_id}")
        
        return {
            "user_id": user_id,
            "busy_slots": busy_slots_data,
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "total_busy_slots": len(busy_slots),
            "timezone": timezone
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching busy slots for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch busy slots: {str(e)}"
        )