import logging
from datetime import time, timedelta, date
from typing import Dict, List, Tuple, Optional, Any
from fastapi import APIRouter, HTTPException, status, Body, Depends
from pydantic import BaseModel, Field, field_validator, model_validator

from db import (
    save_user_preferences,
    get_user_preferences,
    update_user_preferences,
    delete_user_preferences
)
from models import UserPreferences, DayOfWeek, EnergyLevel, ActivityCategory, InputMode, VoiceButtonPosition
from core.security import verify_token

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize an APIRouter instance for user preferences routes
router = APIRouter(
    prefix="/preferences",
    tags=["User Preferences"],
)


# --- Request/Response Models ---
class TimeWindow(BaseModel):
    """Helper model for time windows in requests"""
    start: str = Field(..., description="Start time in HH:MM format")
    end: str = Field(..., description="End time in HH:MM format")
    
    @field_validator('start', 'end')
    @classmethod
    def validate_time_format(cls, v: str):
        """Validates time format HH:MM"""
        try:
            hours, minutes = map(int, v.split(':'))
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise ValueError
            return v
        except:
            raise ValueError(f"Invalid time format: {v}. Use HH:MM format (e.g., '09:00')")


class WorkingHoursInput(BaseModel):
    """Helper model for working hours input"""
    monday: Optional[TimeWindow] = None
    tuesday: Optional[TimeWindow] = None
    wednesday: Optional[TimeWindow] = None
    thursday: Optional[TimeWindow] = None
    friday: Optional[TimeWindow] = None
    saturday: Optional[TimeWindow] = None
    sunday: Optional[TimeWindow] = None


class CreatePreferencesRequest(BaseModel):
    """Request model for creating user preferences"""
    user_id: str = Field(..., description="Unique identifier for the user")
    time_zone: str = Field(..., description="User's primary timezone (e.g., 'Europe/Paris', 'America/New_York')")
    working_hours: WorkingHoursInput = Field(..., description="Working hours for each day of the week")
    preferred_meeting_times: Optional[List[TimeWindow]] = Field(default=None, description="Preferred time windows for meetings")
    days_off: Optional[List[str]] = Field(default=None, description="List of dates (YYYY-MM-DD) when user is unavailable")
    preferred_break_duration_minutes: Optional[int] = Field(default=15, description="Default break duration in minutes")
    work_block_max_duration_minutes: Optional[int] = Field(default=90, description="Maximum continuous work duration in minutes")
    preferred_activity_durations: Optional[Dict[str, int]] = Field(default=None, description="Preferred duration in minutes for activity categories")
    energy_levels: Optional[Dict[str, str]] = Field(default=None, description="Energy levels for different time windows")
    social_preferences: Optional[Dict[str, Any]] = Field(default=None, description="Social scheduling preferences")
    rest_preferences: Optional[Dict[str, Any]] = Field(default=None, description="Rest and sleep preferences")
    input_mode: Optional[str] = Field(default="text", description="User's preferred input mode (text, voice, or both)")
    voice_button_position: Optional[str] = Field(default="right", description="Position of voice button in UI (left or right)")


class UpdatePreferencesRequest(BaseModel):
    """Request model for updating user preferences"""
    time_zone: Optional[str] = Field(None, description="User's primary timezone")
    working_hours: Optional[WorkingHoursInput] = Field(None, description="Working hours for each day of the week")
    preferred_meeting_times: Optional[List[TimeWindow]] = Field(None, description="Preferred time windows for meetings")
    days_off: Optional[List[str]] = Field(None, description="List of dates when user is unavailable")
    preferred_break_duration_minutes: Optional[int] = Field(None, description="Default break duration in minutes")
    work_block_max_duration_minutes: Optional[int] = Field(None, description="Maximum continuous work duration in minutes")
    preferred_activity_durations: Optional[Dict[str, int]] = Field(None, description="Preferred duration in minutes for activity categories")
    energy_levels: Optional[Dict[str, str]] = Field(None, description="Energy levels for different time windows")
    social_preferences: Optional[Dict[str, Any]] = Field(None, description="Social scheduling preferences")
    rest_preferences: Optional[Dict[str, Any]] = Field(None, description="Rest and sleep preferences")
    input_mode: Optional[str] = Field(None, description="User's preferred input mode (text, voice, or both)")
    voice_button_position: Optional[str] = Field(None, description="Position of voice button in UI (left or right)")


class PreferencesResponse(BaseModel):
    """Response model for user preferences"""
    user_id: str
    time_zone: str
    working_hours: Dict[str, TimeWindow]
    preferred_meeting_times: List[TimeWindow]
    days_off: List[str]
    preferred_break_duration_minutes: int
    work_block_max_duration_minutes: int
    preferred_activity_durations: Dict[str, int]
    energy_levels: Dict[str, str]
    social_preferences: Dict[str, Any]
    rest_preferences: Dict[str, Any]
    input_mode: str
    voice_button_position: str
    created_at: int
    updated_at: int


# --- Helper Functions ---
def convert_time_string_to_time(time_str: str) -> time:
    """Convert HH:MM string to time object"""
    hours, minutes = map(int, time_str.split(':'))
    return time(hour=hours, minute=minutes)


def convert_time_to_string(time_obj: time) -> str:
    """Convert time object to HH:MM string"""
    return time_obj.strftime("%H:%M")


def convert_working_hours_input_to_dict(working_hours: WorkingHoursInput) -> Dict[int, Tuple[time, time]]:
    """Convert WorkingHoursInput to the format expected by UserPreferences model"""
    result = {}
    
    day_mapping = {
        'monday': DayOfWeek.MONDAY,
        'tuesday': DayOfWeek.TUESDAY,
        'wednesday': DayOfWeek.WEDNESDAY,
        'thursday': DayOfWeek.THURSDAY,
        'friday': DayOfWeek.FRIDAY,
        'saturday': DayOfWeek.SATURDAY,
        'sunday': DayOfWeek.SUNDAY
    }
    
    for day_name, day_enum in day_mapping.items():
        time_window = getattr(working_hours, day_name)
        if time_window:
            start_time = convert_time_string_to_time(time_window.start)
            end_time = convert_time_string_to_time(time_window.end)
            result[day_enum.value] = (start_time, end_time)
    
    return result


def prepare_preferences_for_dynamodb(preferences: Dict[str, Any]) -> Dict[str, Any]:
    """Convert preferences to DynamoDB-compatible format"""
    # Convert time objects to strings
    if 'working_hours' in preferences:
        working_hours_str = {}
        for day, (start, end) in preferences['working_hours'].items():
            working_hours_str[str(day)] = {
                'start': convert_time_to_string(start),
                'end': convert_time_to_string(end)
            }
        preferences['working_hours'] = working_hours_str
    
    if 'preferred_meeting_times' in preferences:
        meeting_times_str = []
        for start, end in preferences['preferred_meeting_times']:
            meeting_times_str.append({
                'start': convert_time_to_string(start),
                'end': convert_time_to_string(end)
            })
        preferences['preferred_meeting_times'] = meeting_times_str
    
    if 'energy_levels' in preferences:
        energy_levels_str = {}
        for (start, end), level in preferences['energy_levels'].items():
            key = f"{convert_time_to_string(start)}-{convert_time_to_string(end)}"
            energy_levels_str[key] = level.value if hasattr(level, 'value') else level
        preferences['energy_levels'] = energy_levels_str
    
    if 'preferred_activity_duration' in preferences:
        activity_durations_str = {}
        for category, duration in preferences['preferred_activity_duration'].items():
            key = category.value if hasattr(category, 'value') else category
            # Convert timedelta to minutes
            minutes = int(duration.total_seconds() / 60) if isinstance(duration, timedelta) else duration
            activity_durations_str[key] = minutes
        preferences['preferred_activity_duration'] = activity_durations_str
    
    # Convert timedelta fields to minutes
    if 'preferred_break_duration' in preferences:
        duration = preferences['preferred_break_duration']
        preferences['preferred_break_duration_minutes'] = int(duration.total_seconds() / 60)
        del preferences['preferred_break_duration']
    
    if 'work_block_max_duration' in preferences:
        duration = preferences['work_block_max_duration']
        preferences['work_block_max_duration_minutes'] = int(duration.total_seconds() / 60)
        del preferences['work_block_max_duration']
    
    # Convert date objects to strings
    if 'days_off' in preferences:
        preferences['days_off'] = [d.isoformat() if isinstance(d, date) else d for d in preferences['days_off']]
    
    # Convert enum fields to strings
    if 'input_mode' in preferences:
        mode = preferences['input_mode']
        preferences['input_mode'] = mode.value if hasattr(mode, 'value') else mode
    
    if 'voice_button_position' in preferences:
        position = preferences['voice_button_position']
        preferences['voice_button_position'] = position.value if hasattr(position, 'value') else position
    
    return preferences


def convert_dynamodb_to_response(db_prefs: Dict[str, Any]) -> PreferencesResponse:
    """Convert DynamoDB preferences to response format"""
    # Convert working hours
    working_hours_response = {}
    if 'working_hours' in db_prefs:
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for day_num, hours in db_prefs['working_hours'].items():
            if int(day_num) < len(day_names):
                day_name = day_names[int(day_num)]
                working_hours_response[day_name] = TimeWindow(
                    start=hours['start'],
                    end=hours['end']
                )
    
    # Convert preferred meeting times
    meeting_times = []
    if 'preferred_meeting_times' in db_prefs:
        for time_window in db_prefs['preferred_meeting_times']:
            meeting_times.append(TimeWindow(
                start=time_window['start'],
                end=time_window['end']
            ))
    
    return PreferencesResponse(
        user_id=db_prefs['user_id'],
        time_zone=db_prefs.get('time_zone', 'UTC'),
        working_hours=working_hours_response,
        preferred_meeting_times=meeting_times,
        days_off=db_prefs.get('days_off', []),
        preferred_break_duration_minutes=db_prefs.get('preferred_break_duration_minutes', 15),
        work_block_max_duration_minutes=db_prefs.get('work_block_max_duration_minutes', 90),
        preferred_activity_durations=db_prefs.get('preferred_activity_duration', {}),
        energy_levels=db_prefs.get('energy_levels', {}),
        social_preferences=db_prefs.get('social_preferences', {}),
        rest_preferences=db_prefs.get('rest_preferences', {}),
        input_mode=db_prefs.get('input_mode', 'text'),
        voice_button_position=db_prefs.get('voice_button_position', 'right'),
        created_at=db_prefs.get('created_at', 0),
        updated_at=db_prefs.get('updated_at', 0)
    )


# --- API Endpoints ---
@router.post("/{user_id}", response_model=PreferencesResponse)
async def create_user_preferences(
    user_id: str,
    request: CreatePreferencesRequest = Body(...),
    current_user_id: str = Depends(verify_token)
) -> PreferencesResponse:
    """
    Create or replace user preferences.
    
    If preferences already exist for the user, they will be completely replaced
    with the new preferences provided in the request.
    
    Args:
        user_id: The user ID to create/replace preferences for
        request: The preferences data
        
    Returns:
        PreferencesResponse with created/replaced preferences
        
    Raises:
        HTTPException: If creation/replacement fails
    """
    logger.info(f"Creating/replacing preferences for user {user_id}")
    
    # Verify that the authenticated user can only create their own preferences
    if current_user_id != user_id:
        logger.warning(f"User {current_user_id} attempted to create preferences for user {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only create your own preferences"
        )
    
    # Check if preferences already exist - if they do, we'll replace them
    existing = get_user_preferences(user_id)
    if existing:
        logger.info(f"Preferences already exist for user {user_id}. Replacing with new preferences.")
        # Delete existing preferences first to ensure clean replacement
        delete_result = delete_user_preferences(user_id)
        if not delete_result:
            logger.error(f"Failed to delete existing preferences for user {user_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to replace existing preferences"
            )
    
    # Validate user_id matches
    if request.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID in path does not match user ID in request body"
        )
    
    try:
        # Convert request to UserPreferences model for validation
        working_hours = convert_working_hours_input_to_dict(request.working_hours)
        
        # Prepare preferences data
        preferences_data = {
            'user_id': user_id,
            'time_zone': request.time_zone,
            'working_hours': working_hours,
            'days_off': [date.fromisoformat(d) for d in (request.days_off or [])],
            'preferred_break_duration': timedelta(minutes=request.preferred_break_duration_minutes),
            'work_block_max_duration': timedelta(minutes=request.work_block_max_duration_minutes)
        }
        
        # Add optional fields
        if request.preferred_meeting_times:
            preferences_data['preferred_meeting_times'] = [
                (convert_time_string_to_time(t.start), convert_time_string_to_time(t.end))
                for t in request.preferred_meeting_times
            ]
        
        if request.preferred_activity_durations:
            preferences_data['preferred_activity_duration'] = {
                ActivityCategory(k): timedelta(minutes=v)
                for k, v in request.preferred_activity_durations.items()
            }
        
        if request.energy_levels:
            energy_levels = {}
            for time_key, level in request.energy_levels.items():
                start_str, end_str = time_key.split('-')
                start_time = convert_time_string_to_time(start_str)
                end_time = convert_time_string_to_time(end_str)
                energy_levels[(start_time, end_time)] = EnergyLevel(level)
            preferences_data['energy_levels'] = energy_levels
        
        if request.social_preferences:
            preferences_data['social_preferences'] = request.social_preferences
        
        if request.rest_preferences:
            preferences_data['rest_preferences'] = request.rest_preferences
        
        if request.input_mode:
            preferences_data['input_mode'] = InputMode(request.input_mode)
        
        if request.voice_button_position:
            preferences_data['voice_button_position'] = VoiceButtonPosition(request.voice_button_position)
        
        # Validate with UserPreferences model
        user_prefs = UserPreferences(**preferences_data)
        
        # Convert to DynamoDB format
        db_prefs = prepare_preferences_for_dynamodb(user_prefs.model_dump())
        
        # Save to DynamoDB
        result = save_user_preferences(db_prefs)
        if result != "success":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save preferences: {result}"
            )
        
        # Retrieve and return the saved preferences
        saved_prefs = get_user_preferences(user_id)
        if not saved_prefs:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve saved preferences"
            )
        
        return convert_dynamodb_to_response(saved_prefs)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating preferences for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create preferences: {str(e)}"
        )


@router.get("/{user_id}", response_model=PreferencesResponse)
async def get_preferences(
    user_id: str,
    current_user_id: str = Depends(verify_token)
) -> PreferencesResponse:
    """
    Retrieve user preferences.
    
    Args:
        user_id: The user ID to get preferences for
        
    Returns:
        PreferencesResponse with user preferences
        
    Raises:
        HTTPException: If preferences not found
    """
    logger.info(f"Retrieving preferences for user {user_id}")
    
    # Verify that the authenticated user can only get their own preferences
    if current_user_id != user_id:
        logger.warning(f"User {current_user_id} attempted to get preferences for user {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own preferences"
        )
    
    preferences = get_user_preferences(user_id)
    if not preferences:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preferences not found for user {user_id}"
        )
    
    return convert_dynamodb_to_response(preferences)


@router.put("/{user_id}")
async def update_preferences(
    user_id: str,
    request: UpdatePreferencesRequest = Body(...),
    current_user_id: str = Depends(verify_token)
) -> Dict[str, str]:
    """
    Update existing user preferences.
    
    Args:
        user_id: The user ID to update preferences for
        request: The fields to update
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If preferences not found or update fails
    """
    logger.info(f"Updating preferences for user {user_id}")
    
    # Verify that the authenticated user can only update their own preferences
    if current_user_id != user_id:
        logger.warning(f"User {current_user_id} attempted to update preferences for user {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own preferences"
        )
    
    # Check if preferences exist
    existing = get_user_preferences(user_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preferences not found for user {user_id}. Use POST to create."
        )
    
    try:
        # Prepare updates
        updates = {}
        
        if request.time_zone is not None:
            updates['time_zone'] = request.time_zone
        
        if request.working_hours is not None:
            working_hours = convert_working_hours_input_to_dict(request.working_hours)
            updates['working_hours'] = working_hours
        
        if request.preferred_meeting_times is not None:
            updates['preferred_meeting_times'] = [
                (convert_time_string_to_time(t.start), convert_time_string_to_time(t.end))
                for t in request.preferred_meeting_times
            ]
        
        if request.days_off is not None:
            updates['days_off'] = [date.fromisoformat(d) for d in request.days_off]
        
        if request.preferred_break_duration_minutes is not None:
            updates['preferred_break_duration'] = timedelta(minutes=request.preferred_break_duration_minutes)
        
        if request.work_block_max_duration_minutes is not None:
            updates['work_block_max_duration'] = timedelta(minutes=request.work_block_max_duration_minutes)
        
        if request.preferred_activity_durations is not None:
            updates['preferred_activity_duration'] = {
                ActivityCategory(k): timedelta(minutes=v)
                for k, v in request.preferred_activity_durations.items()
            }
        
        if request.energy_levels is not None:
            energy_levels = {}
            for time_key, level in request.energy_levels.items():
                start_str, end_str = time_key.split('-')
                start_time = convert_time_string_to_time(start_str)
                end_time = convert_time_string_to_time(end_str)
                energy_levels[(start_time, end_time)] = EnergyLevel(level)
            updates['energy_levels'] = energy_levels
        
        if request.social_preferences is not None:
            updates['social_preferences'] = request.social_preferences
        
        if request.rest_preferences is not None:
            updates['rest_preferences'] = request.rest_preferences
        
        if request.input_mode is not None:
            updates['input_mode'] = InputMode(request.input_mode)
        
        if request.voice_button_position is not None:
            updates['voice_button_position'] = VoiceButtonPosition(request.voice_button_position)
        
        if not updates:
            return {"message": "No fields to update"}
        
        # Convert to DynamoDB format
        db_updates = prepare_preferences_for_dynamodb(updates)
        
        # Update in DynamoDB
        result = update_user_preferences(user_id, db_updates)
        if result != "success":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update preferences: {result}"
            )
        
        return {"message": f"Successfully updated preferences for user {user_id}"}
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating preferences for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update preferences: {str(e)}"
        )


@router.delete("/{user_id}")
async def reset_preferences(
    user_id: str,
    current_user_id: str = Depends(verify_token)
) -> Dict[str, str]:
    """
    Reset (delete) user preferences.
    
    Args:
        user_id: The user ID to reset preferences for
        
    Returns:
        Success message
        
    Raises:
        HTTPException: If deletion fails
    """
    logger.info(f"Resetting preferences for user {user_id}")
    
    # Verify that the authenticated user can only reset their own preferences
    if current_user_id != user_id:
        logger.warning(f"User {current_user_id} attempted to reset preferences for user {user_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only reset your own preferences"
        )
    
    # Check if preferences exist
    existing = get_user_preferences(user_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preferences not found for user {user_id}"
        )
    
    # Delete preferences
    success = delete_user_preferences(user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset preferences"
        )
    
    return {"message": f"Successfully reset preferences for user {user_id}"}