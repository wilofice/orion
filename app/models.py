from datetime import date, datetime, time, timedelta
from pydantic import BaseModel

class Event(BaseModel):
    startTime: time
    endTime: time
    endDate: date
    startDate: date
    topic: str
    description: str
    attendees: list[str]

# app/models.py
import uuid
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

import pytz  # Recommended for robust timezone handling
from pydantic import (BaseModel, Field, field_validator,
                      model_validator)


# --- Enums ---

class PriorityLevel(str, Enum):
    """Enum for MustDoActivity priority levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class ActivityCategory(str, Enum):
    """Enum for WantToDoActivity categories."""
    WORK = "WORK"
    PERSONAL = "PERSONAL"
    LEARNING = "LEARNING"
    EXERCISE = "EXERCISE"
    SOCIAL = "SOCIAL"
    CHORE = "CHORE"
    ERRAND = "ERRAND"
    OTHER = "OTHER" # Added for flexibility
    FUN = "FUN" # Added for flexibility

class ActivityStatus(str, Enum):
    """Enum for WantToDoActivity status."""
    TODO = "TODO"
    SCHEDULED = "SCHEDULED"
    DONE = "DONE"

class EnergyLevel(str, Enum):
    """Enum for user energy levels at different times."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class DayOfWeek(int, Enum):
    """Enum for days of the week (Monday=0, Sunday=6)."""
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

class InputMode(str, Enum):
    """Enum for user input mode preferences."""
    TEXT = "text"
    VOICE = "voice"
    BOTH = "both"

class VoiceButtonPosition(str, Enum):
    """Enum for voice button position in UI."""
    LEFT = "left"
    RIGHT = "right"

# --- Core Models ---

class TimeSlot(BaseModel):
    """Represents a continuous block of time."""
    start_time: datetime = Field(..., description="The inclusive start time of the slot (timezone-aware).")
    end_time: datetime = Field(..., description="The exclusive end time of the slot (timezone-aware).")

    @field_validator('start_time', 'end_time')
    @classmethod
    def check_timezone_awareness(cls, v: datetime):
        """Ensures datetime objects are timezone-aware."""
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            # Or default to UTC/local timezone if appropriate for the application
            raise ValueError("datetime must be timezone-aware")
        return v

    @model_validator(mode='after')
    def check_end_time_after_start_time(self):
        """Validates that end_time is strictly after start_time."""
        if self.start_time >= self.end_time:
            raise ValueError("end_time must be strictly after start_time")
        return self

    @property
    def duration(self) -> timedelta:
        """Calculates the duration of the time slot."""
        return self.end_time - self.start_time

    def __str__(self):
        """Provides a user-friendly string representation."""
        return f"TimeSlot(start={self.start_time}, end={self.end_time}, duration={self.duration})"

class MustDoActivity(BaseModel):
    """Represents a fixed, non-negotiable activity or event."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for the activity.")
    title: str = Field(..., description="Concise name or title of the activity.")
    description: Optional[str] = Field(None, description="Optional longer description of the activity.")
    start_time: datetime = Field(..., description="The fixed start time of the activity (timezone-aware).")
    end_time: datetime = Field(..., description="The fixed end time of the activity (timezone-aware).")
    priority: PriorityLevel = Field(..., description="Priority level of the activity.")
    source_calendar_id: Optional[str] = Field(None, description="Identifier of the source calendar (e.g., 'primary').")
    source_event_id: Optional[str] = Field(None, description="Identifier of the event in the source calendar.")

    @field_validator('start_time', 'end_time')
    @classmethod
    def check_timezone_awareness(cls, v: datetime):
        """Ensures datetime objects are timezone-aware."""
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("datetime must be timezone-aware")
        return v

    @model_validator(mode='after')
    def check_end_time_after_start_time(self):
        """Validates that end_time is strictly after start_time."""
        if self.start_time >= self.end_time:
            raise ValueError("end_time must be strictly after start_time")
        return self

    @property
    def duration(self) -> timedelta:
        """Calculates the duration of the activity."""
        return self.end_time - self.start_time

class WantToDoActivity(BaseModel):
    """Represents a flexible task or activity the user wants to accomplish."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for the activity.")
    title: str = Field(..., description="Concise name or title of the activity.")
    description: Optional[str] = Field(None, description="Optional longer description of the activity.")
    estimated_duration: timedelta = Field(..., description="Estimated time required to complete the activity.")
    priority: int = Field(..., ge=1, le=10, description="User-defined priority (e.g., 1-10, higher is more important).")
    deadline: Optional[datetime] = Field(None, description="Optional deadline for completing the activity (timezone-aware).")
    category: ActivityCategory = Field(..., description="Category the activity belongs to.")
    # Tuple[start_time, end_time] - naive time objects representing preferred window on any day
    preferred_time_window: Optional[Tuple[time, time]] = Field(None, description="Optional preferred time window (e.g., (9:00, 12:00)) for scheduling.")
    required_location: Optional[str] = Field(None, description="Optional specific location required for the activity.")
    status: ActivityStatus = Field(default=ActivityStatus.TODO, description="Current status of the activity.")

    @field_validator('estimated_duration')
    @classmethod
    def check_positive_duration(cls, v: timedelta):
        """Validates that estimated_duration is positive."""
        if v <= timedelta(0):
            raise ValueError("estimated_duration must be positive")
        return v

    @field_validator('deadline')
    @classmethod
    def check_timezone_awareness(cls, v: Optional[datetime]):
        """Ensures deadline datetime object is timezone-aware if provided."""
        if v and (v.tzinfo is None or v.tzinfo.utcoffset(v) is None):
            raise ValueError("deadline datetime must be timezone-aware")
        return v

    @field_validator('preferred_time_window')
    @classmethod
    def check_preferred_time_window_order(cls, v: Optional[Tuple[time, time]]):
        """Validates that the end time in preferred_time_window is after the start time."""
        if v and v[0] >= v[1]:
            raise ValueError("preferred_time_window end time must be after start time")
        return v

def get_default_working_hours() -> Dict[DayOfWeek, Tuple[time, time]]:
    """Returns default working hours: Mon-Fri 9am-5pm with lunch break 12:30pm-1:30pm."""
    # Note: Since we can't have a break in the middle, we'll use 9am-5pm continuous
    # The lunch break can be handled separately through preferred_break_times or other mechanisms
    default_hours = {
        DayOfWeek.MONDAY: (time(9, 0), time(17, 0)),
        DayOfWeek.TUESDAY: (time(9, 0), time(17, 0)),
        DayOfWeek.WEDNESDAY: (time(9, 0), time(17, 0)),
        DayOfWeek.THURSDAY: (time(9, 0), time(17, 0)),
        DayOfWeek.FRIDAY: (time(9, 0), time(17, 0)),
    }
    return default_hours

class UserPreferences(BaseModel):
    """Stores user-specific preferences influencing scheduling."""
    user_id: str = Field(..., description="Unique identifier for the user.")
    # Maps DayOfWeek enum (Mon=0) to a tuple of (start_time, end_time) naive time objects
    working_hours: Dict[DayOfWeek, Tuple[time, time]] = Field(default_factory=get_default_working_hours, description="Dictionary mapping weekday (Mon=0) to working start and end times.")
    # List of preferred meeting windows, naive time objects
    preferred_meeting_times: Optional[List[Tuple[time, time]]] = Field(default_factory=list, description="Optional list of preferred time windows for meetings.")
    # List of specific dates the user is off
    days_off: List[date] = Field(default_factory=list, description="List of specific dates the user is unavailable.")
    time_zone: str = Field(default="UTC", description="User's primary timezone (e.g., 'Europe/Paris', 'America/New_York').")
    preferred_break_duration: timedelta = Field(default=timedelta(minutes=15), description="Default duration for automatically scheduled breaks.")
    work_block_max_duration: timedelta = Field(default=timedelta(hours=1), description="Maximum duration of continuous work before suggesting a break.")
    # Optional mapping of activity category to a preferred duration
    preferred_activity_duration: Optional[Dict[ActivityCategory, timedelta]] = Field(default_factory=dict, description="Optional preferred duration for specific activity categories.")
    # Optional mapping of a time tuple (start, end) to energy level - naive time objects
    energy_levels: Optional[Dict[Tuple[time, time], EnergyLevel]] = Field(default_factory=dict, description="Optional mapping of time windows to expected energy levels.")
    # Flexible dictionary for social preferences, e.g., {"preferred_meeting_days": [DayOfWeek.TUESDAY, DayOfWeek.THURSDAY]}
    social_preferences: Dict = Field(default_factory=dict, description="Flexible dictionary for social scheduling preferences.")
    # Flexible dictionary for rest, e.g., {"sleep_schedule": (time(23,0), time(7,0))} - naive time objects
    rest_preferences: Dict = Field(default_factory=dict, description="Flexible dictionary for rest and sleep preferences.")
    # Input mode preference for the user interface
    input_mode: InputMode = Field(default=InputMode.TEXT, description="User's preferred input mode (text, voice, or both).")
    # Voice button position preference for the user interface
    voice_button_position: VoiceButtonPosition = Field(default=VoiceButtonPosition.RIGHT, description="Position of the voice button in the UI (left or right).")

    @field_validator('time_zone')
    @classmethod
    def check_valid_timezone(cls, v: str):
        """Validates that the provided timezone string is valid."""
        # If empty string is provided, use default UTC
        if not v:
            return "UTC"
        if v not in pytz.all_timezones_set:
            raise ValueError(f"Invalid timezone string: {v}")
        return v

    @field_validator('working_hours')
    @classmethod
    def check_working_hours(cls, v: Dict[DayOfWeek, Tuple[time, time]]):
        """Validates working hours format and logic."""
        # Allow empty dict - the default factory will provide default values
        if not v:
            return get_default_working_hours()
        for day, hours in v.items():
            if not isinstance(day, DayOfWeek):
                 raise ValueError(f"Invalid day key in working_hours: {day}. Use DayOfWeek enum.")
            if not isinstance(hours, tuple) or len(hours) != 2 or not all(isinstance(t, time) for t in hours):
                raise ValueError(f"Invalid time tuple format for day {day}: {hours}. Expected (start_time, end_time).")
            if hours[0] >= hours[1]:
                raise ValueError(f"Working hours end time must be after start time for day {day}: {hours}")
        return v

    @field_validator('preferred_meeting_times', 'energy_levels', 'rest_preferences')
    @classmethod
    def check_time_tuple_keys_and_values(cls, v, info):
        """Generic validator for dicts using time tuples as keys or values."""
        if isinstance(v, list): # For preferred_meeting_times
            for item in v:
                 if not isinstance(item, tuple) or len(item) != 2 or not all(isinstance(t, time) for t in item):
                     raise ValueError(f"Invalid time tuple format in {info.field_name}: {item}. Expected (start_time, end_time).")
                 if item[0] >= item[1]:
                     raise ValueError(f"End time must be after start time in {info.field_name}: {item}")
        elif isinstance(v, dict): # For energy_levels, rest_preferences (if using time tuples)
            for key, value in v.items():
                # Check keys if they are time tuples (e.g., energy_levels)
                if isinstance(key, tuple):
                    if len(key) != 2 or not all(isinstance(t, time) for t in key):
                        raise ValueError(f"Invalid time tuple format for key in {info.field_name}: {key}. Expected (start_time, end_time).")
                    if key[0] >= key[1]:
                        raise ValueError(f"End time must be after start time for key in {info.field_name}: {key}")
                # Check values if they are time tuples (e.g., rest_preferences['sleep_schedule'])
                if isinstance(value, tuple):
                     if len(value) != 2 or not all(isinstance(t, time) for t in value):
                         raise ValueError(f"Invalid time tuple format for value in {info.field_name} (key={key}): {value}. Expected (start_time, end_time).")
                     # Note: Sleep schedule can cross midnight, so start >= end is allowed here.

        return v

    @field_validator('preferred_break_duration', 'work_block_max_duration')
    @classmethod
    def check_positive_timedelta(cls, v: timedelta, info):
        """Ensures specific timedelta fields are positive."""
        if v <= timedelta(0):
            raise ValueError(f"{info.field_name} must be positive")
        return v

    @field_validator('preferred_activity_duration')
    @classmethod
    def check_preferred_activity_duration(cls, v: Optional[Dict[ActivityCategory, timedelta]]):
        """Validates preferred activity durations."""
        if v:
            for category, duration in v.items():
                if not isinstance(category, ActivityCategory):
                    raise ValueError(f"Invalid category key in preferred_activity_duration: {category}. Use ActivityCategory enum.")
                if not isinstance(duration, timedelta) or duration <= timedelta(0):
                    raise ValueError(f"Invalid or non-positive duration for category {category}: {duration}")
        return v


class ChatRequest(BaseModel):
    """Request model for the chat prompt endpoint."""
    user_id: str = Field(..., description="Unique identifier for the user making the request.")
    session_id: Optional[str] = Field(None, description="Optional identifier for the ongoing chat session. Helps maintain conversation history.")
    prompt_text: str = Field(..., description="The natural language input from the user or transcribed audio content.")
    audio_url: Optional[str] = Field(None, description="Optional URL of the audio file stored in S3 for voice messages.")
    client_context: Optional[Dict[str, Any]] = Field(None, description="Optional arbitrary JSON object providing client-side context (e.g., current view, timezone).")

class ResponseStatus(str, Enum):
    """Enum for the status field in ChatResponse."""
    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    ERROR = "error"

class ChatResponse(BaseModel):
    """Response model for a successful chat prompt processing."""
    session_id: str = Field(..., description="Identifier for the chat session (can be new or existing).")
    status: ResponseStatus = Field(..., description="Indicates the outcome of processing the prompt.")
    response_text: Optional[str] = Field(None, description="The natural language response to be displayed to the user. Required unless status is 'error'.")
    clarification_options: Optional[List[str]] = Field(None, description="Optional list of suggestions or options if status is 'needs_clarification'.")

class ErrorDetail(BaseModel):
    """Schema for standard error responses."""
    error_code: str = Field(..., description="A unique code identifying the type of error.")
    message: str = Field(..., description="A user-friendly error message.")
    details: Optional[Dict[str, Any]] = Field(None, description="Optional additional details about the error.")
