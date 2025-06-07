"""Tests for UserPreferences model default values."""
import pytest
from datetime import time, timedelta
from app.models import UserPreferences, DayOfWeek, get_default_working_hours


def test_user_preferences_with_minimal_data():
    """Test that UserPreferences can be created with just user_id."""
    # Should not raise validation errors
    prefs = UserPreferences(user_id="test_user")
    
    # Check defaults are applied
    assert prefs.user_id == "test_user"
    assert prefs.time_zone == "UTC"
    assert prefs.preferred_break_duration == timedelta(minutes=15)
    assert prefs.work_block_max_duration == timedelta(hours=1)
    
    # Check working hours defaults
    assert len(prefs.working_hours) == 5  # Mon-Fri
    assert DayOfWeek.MONDAY in prefs.working_hours
    assert DayOfWeek.FRIDAY in prefs.working_hours
    assert DayOfWeek.SATURDAY not in prefs.working_hours
    assert DayOfWeek.SUNDAY not in prefs.working_hours
    
    # Check working hours are 9am-5pm
    for day in [DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY, 
                DayOfWeek.THURSDAY, DayOfWeek.FRIDAY]:
        start, end = prefs.working_hours[day]
        assert start == time(9, 0)
        assert end == time(17, 0)


def test_user_preferences_with_empty_values():
    """Test that UserPreferences handles empty values properly."""
    # This should not raise validation errors
    prefs = UserPreferences(
        user_id="test_user",
        time_zone="",  # Empty string should default to UTC
        working_hours={}  # Empty dict should get defaults
    )
    
    assert prefs.time_zone == "UTC"
    assert len(prefs.working_hours) == 5  # Should have default Mon-Fri


def test_user_preferences_with_zero_durations():
    """Test that UserPreferences validates positive durations."""
    # This should raise validation error for zero durations
    with pytest.raises(ValueError, match="preferred_break_duration must be positive"):
        UserPreferences(
            user_id="test_user",
            preferred_break_duration=timedelta(0)
        )
    
    with pytest.raises(ValueError, match="work_block_max_duration must be positive"):
        UserPreferences(
            user_id="test_user",
            work_block_max_duration=timedelta(0)
        )


def test_get_default_working_hours():
    """Test the default working hours function."""
    defaults = get_default_working_hours()
    
    # Should have Mon-Fri
    assert len(defaults) == 5
    
    # Check all weekdays are present
    for day in [DayOfWeek.MONDAY, DayOfWeek.TUESDAY, DayOfWeek.WEDNESDAY,
                DayOfWeek.THURSDAY, DayOfWeek.FRIDAY]:
        assert day in defaults
        start, end = defaults[day]
        assert start == time(9, 0)
        assert end == time(17, 0)
    
    # Weekend should not be present
    assert DayOfWeek.SATURDAY not in defaults
    assert DayOfWeek.SUNDAY not in defaults


def test_user_preferences_override_defaults():
    """Test that provided values override defaults."""
    custom_hours = {
        DayOfWeek.MONDAY: (time(8, 0), time(16, 0)),
        DayOfWeek.TUESDAY: (time(10, 0), time(18, 0))
    }
    
    prefs = UserPreferences(
        user_id="test_user",
        time_zone="America/New_York",
        working_hours=custom_hours,
        preferred_break_duration=timedelta(minutes=30),
        work_block_max_duration=timedelta(hours=2)
    )
    
    assert prefs.time_zone == "America/New_York"
    assert prefs.working_hours == custom_hours
    assert prefs.preferred_break_duration == timedelta(minutes=30)
    assert prefs.work_block_max_duration == timedelta(hours=2)


def test_user_preferences_all_fields():
    """Test UserPreferences with all fields populated."""
    prefs = UserPreferences(
        user_id="test_user",
        time_zone="Europe/London",
        working_hours=get_default_working_hours(),
        preferred_meeting_times=[(time(10, 0), time(11, 0))],
        days_off=[],
        preferred_break_duration=timedelta(minutes=20),
        work_block_max_duration=timedelta(minutes=90),
        preferred_activity_duration={},
        energy_levels={},
        social_preferences={"preferred_days": ["Tuesday"]},
        rest_preferences={"lunch_break": "12:30-13:30"},
        input_mode="both",
        voice_button_position="left"
    )
    
    assert prefs.user_id == "test_user"
    assert prefs.time_zone == "Europe/London"
    assert len(prefs.working_hours) == 5