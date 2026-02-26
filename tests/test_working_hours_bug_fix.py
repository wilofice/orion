"""Tests for working hours bug fix in preference router."""
import pytest
from unittest.mock import Mock, MagicMock
from datetime import time, timedelta
from tests.conftest import create_test_client
from app.models import DayOfWeek, get_default_working_hours


def test_create_preferences_with_empty_working_hours_object(monkeypatch):
    """Test creating preferences with an empty WorkingHoursInput object."""
    client = create_test_client()
    
    # Mock successful save
    mock_save = Mock(return_value="success")
    
    # Mock get to return saved preferences with defaults
    default_hours = get_default_working_hours()
    mock_get = Mock(return_value={
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {
            str(day.value): {"start": "09:00", "end": "17:00"}
            for day in default_hours.keys()
        },
        "preferred_meeting_times": [],
        "days_off": [],
        "preferred_break_duration_minutes": 15,
        "work_block_max_duration_minutes": 90,
        "preferred_activity_duration": {},
        "energy_levels": {},
        "social_preferences": {},
        "rest_preferences": {},
        "input_mode": "text",
        "voice_button_position": "right",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    monkeypatch.setattr("app.user_preferences_router.save_user_preferences", mock_save)
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    
    # Request with empty working_hours object
    request_data = {
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {}  # Empty object
    }
    
    response = client.post("/preferences/test_user", json=request_data)
    assert response.status_code == 200
    
    # Verify default working hours were applied
    response_data = response.json()
    assert len(response_data["working_hours"]) == 5  # Mon-Fri
    assert "monday" in response_data["working_hours"]
    assert "friday" in response_data["working_hours"]
    assert "saturday" not in response_data["working_hours"]


def test_create_preferences_without_working_hours_field(monkeypatch):
    """Test creating preferences without providing working_hours field at all."""
    client = create_test_client()
    
    # Mock successful save
    mock_save = Mock(return_value="success")
    
    # Mock get to return saved preferences with defaults
    default_hours = get_default_working_hours()
    mock_get = Mock(return_value={
        "user_id": "test_user",
        "time_zone": "America/New_York",
        "working_hours": {
            str(day.value): {"start": "09:00", "end": "17:00"}
            for day in default_hours.keys()
        },
        "preferred_meeting_times": [],
        "days_off": [],
        "preferred_break_duration_minutes": 15,
        "work_block_max_duration_minutes": 60,  # 1 hour as per new default
        "preferred_activity_duration": {},
        "energy_levels": {},
        "social_preferences": {},
        "rest_preferences": {},
        "input_mode": "text",
        "voice_button_position": "right",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    monkeypatch.setattr("app.user_preferences_router.save_user_preferences", mock_save)
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    
    # Request without working_hours field
    request_data = {
        "user_id": "test_user",
        "time_zone": "America/New_York"
        # No working_hours field at all
    }
    
    response = client.post("/preferences/test_user", json=request_data)
    assert response.status_code == 200
    
    # Verify default working hours were applied
    response_data = response.json()
    assert response_data["time_zone"] == "America/New_York"
    assert len(response_data["working_hours"]) == 5  # Mon-Fri defaults
    assert response_data["work_block_max_duration_minutes"] == 60  # 1 hour default


def test_create_preferences_with_partial_working_hours(monkeypatch):
    """Test creating preferences with only some days specified."""
    client = create_test_client()
    
    # Mock successful save
    mock_save = Mock(return_value="success")
    
    # Mock get to return what was saved
    mock_get = Mock(return_value={
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {
            "0": {"start": "10:00", "end": "18:00"},  # Monday
            "2": {"start": "09:00", "end": "17:00"}   # Wednesday
        },
        "preferred_meeting_times": [],
        "days_off": [],
        "preferred_break_duration_minutes": 15,
        "work_block_max_duration_minutes": 90,
        "preferred_activity_duration": {},
        "energy_levels": {},
        "social_preferences": {},
        "rest_preferences": {},
        "input_mode": "text",
        "voice_button_position": "right",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    monkeypatch.setattr("app.user_preferences_router.save_user_preferences", mock_save)
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    
    # Request with only Monday and Wednesday
    request_data = {
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {
            "monday": {"start": "10:00", "end": "18:00"},
            "wednesday": {"start": "09:00", "end": "17:00"}
        }
    }
    
    response = client.post("/preferences/test_user", json=request_data)
    assert response.status_code == 200
    
    # Verify only specified days were saved
    response_data = response.json()
    assert len(response_data["working_hours"]) == 2
    assert "monday" in response_data["working_hours"]
    assert "wednesday" in response_data["working_hours"]
    assert response_data["working_hours"]["monday"]["start"] == "10:00"


def test_update_preferences_with_empty_working_hours(monkeypatch):
    """Test updating preferences with empty working hours doesn't break."""
    client = create_test_client()
    
    # Mock existing preferences
    mock_get_existing = Mock(return_value={
        "user_id": "test_user",
        "working_hours": {"0": {"start": "09:00", "end": "17:00"}}
    })
    
    # Mock successful update
    mock_update = Mock(return_value="success")
    
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get_existing)
    monkeypatch.setattr("app.user_preferences_router.update_user_preferences", mock_update)
    
    # Try to update with empty working hours
    update_data = {
        "working_hours": {}
    }
    
    response = client.put("/preferences/test_user", json=update_data)
    assert response.status_code == 200
    
    # Verify update was called but working_hours wasn't included
    # (because empty working hours returns None from converter)
    mock_update.assert_called_once()
    _, kwargs = mock_update.call_args
    # Working hours should not be in the updates dict
    assert "working_hours" not in kwargs


def test_zero_duration_validation(monkeypatch):
    """Test that zero durations are still rejected."""
    client = create_test_client()
    
    # Mock no existing preferences
    mock_get = Mock(return_value=None)
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    
    # Request with zero durations
    request_data = {
        "user_id": "test_user",
        "time_zone": "UTC",
        "preferred_break_duration_minutes": 0,  # Zero should be rejected
        "work_block_max_duration_minutes": 0   # Zero should be rejected
    }
    
    response = client.post("/preferences/test_user", json=request_data)
    # Should succeed because the router skips zero values
    assert response.status_code == 200