"""Tests for new user preference fields (input_mode and voice_button_position)."""
import pytest
from unittest.mock import Mock
from tests.conftest import create_test_client
from app.models import InputMode, VoiceButtonPosition


def test_create_preferences_with_input_mode_and_voice_position(monkeypatch):
    """Test creating preferences with new input mode and voice button position fields."""
    client = create_test_client()
    
    # Mock the database operations
    mock_save = Mock(return_value="success")
    mock_get = Mock(return_value={
        "user_id": "test_user",
        "time_zone": "America/New_York",
        "working_hours": {
            "0": {"start": "09:00", "end": "17:00"},
            "1": {"start": "09:00", "end": "17:00"}
        },
        "preferred_meeting_times": [],
        "days_off": [],
        "preferred_break_duration_minutes": 15,
        "work_block_max_duration_minutes": 90,
        "preferred_activity_duration": {},
        "energy_levels": {},
        "social_preferences": {},
        "rest_preferences": {},
        "input_mode": "both",
        "voice_button_position": "left",
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    monkeypatch.setattr("app.user_preferences_router.save_user_preferences", mock_save)
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    
    request_data = {
        "user_id": "test_user",
        "time_zone": "America/New_York",
        "working_hours": {
            "monday": {"start": "09:00", "end": "17:00"},
            "tuesday": {"start": "09:00", "end": "17:00"}
        },
        "input_mode": "both",
        "voice_button_position": "left"
    }
    
    response = client.post("/preferences/test_user", json=request_data)
    assert response.status_code == 200
    
    response_data = response.json()
    assert response_data["input_mode"] == "both"
    assert response_data["voice_button_position"] == "left"


def test_update_preferences_with_input_mode(monkeypatch):
    """Test updating preferences with input mode field."""
    client = create_test_client()
    
    # Mock existing preferences
    mock_get = Mock(return_value={
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {"0": {"start": "09:00", "end": "17:00"}},
        "input_mode": "text",
        "voice_button_position": "right"
    })
    mock_update = Mock(return_value="success")
    
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    monkeypatch.setattr("app.user_preferences_router.update_user_preferences", mock_update)
    
    update_data = {
        "input_mode": "voice"
    }
    
    response = client.put("/preferences/test_user", json=update_data)
    assert response.status_code == 200
    
    # Verify update was called with correct data
    mock_update.assert_called_once()
    _, call_args = mock_update.call_args
    assert "input_mode" in call_args
    assert call_args["input_mode"] == "voice"


def test_update_preferences_with_voice_button_position(monkeypatch):
    """Test updating preferences with voice button position field."""
    client = create_test_client()
    
    # Mock existing preferences
    mock_get = Mock(return_value={
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {"0": {"start": "09:00", "end": "17:00"}},
        "input_mode": "both",
        "voice_button_position": "right"
    })
    mock_update = Mock(return_value="success")
    
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    monkeypatch.setattr("app.user_preferences_router.update_user_preferences", mock_update)
    
    update_data = {
        "voice_button_position": "left"
    }
    
    response = client.put("/preferences/test_user", json=update_data)
    assert response.status_code == 200
    
    # Verify update was called with correct data
    mock_update.assert_called_once()
    _, call_args = mock_update.call_args
    assert "voice_button_position" in call_args
    assert call_args["voice_button_position"] == "left"


def test_get_preferences_returns_default_input_fields(monkeypatch):
    """Test that GET preferences returns default values for new fields if not set."""
    client = create_test_client()
    
    # Mock preferences without new fields (simulating old data)
    mock_get = Mock(return_value={
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {
            "0": {"start": "09:00", "end": "17:00"}
        },
        "preferred_meeting_times": [],
        "days_off": [],
        "created_at": 1234567890,
        "updated_at": 1234567890
    })
    
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    
    response = client.get("/preferences/test_user")
    assert response.status_code == 200
    
    response_data = response.json()
    # Should have default values
    assert response_data["input_mode"] == "text"
    assert response_data["voice_button_position"] == "right"


def test_invalid_input_mode_value(monkeypatch):
    """Test that invalid input mode values are rejected."""
    client = create_test_client()
    
    # Mock to simulate no existing preferences
    mock_get = Mock(return_value=None)
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    
    request_data = {
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {
            "monday": {"start": "09:00", "end": "17:00"}
        },
        "input_mode": "invalid_mode"  # Invalid value
    }
    
    response = client.post("/preferences/test_user", json=request_data)
    assert response.status_code == 400  # Should fail validation


def test_invalid_voice_button_position_value(monkeypatch):
    """Test that invalid voice button position values are rejected."""
    client = create_test_client()
    
    # Mock to simulate no existing preferences
    mock_get = Mock(return_value=None)
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    
    request_data = {
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {
            "monday": {"start": "09:00", "end": "17:00"}
        },
        "voice_button_position": "center"  # Invalid value (only left/right allowed)
    }
    
    response = client.post("/preferences/test_user", json=request_data)
    assert response.status_code == 400  # Should fail validation


def test_all_input_mode_values():
    """Test that all InputMode enum values are valid."""
    assert InputMode.TEXT.value == "text"
    assert InputMode.VOICE.value == "voice"
    assert InputMode.BOTH.value == "both"


def test_all_voice_button_position_values():
    """Test that all VoiceButtonPosition enum values are valid."""
    assert VoiceButtonPosition.LEFT.value == "left"
    assert VoiceButtonPosition.RIGHT.value == "right"


def test_preferences_with_both_new_fields(monkeypatch):
    """Test creating and retrieving preferences with both new fields set."""
    client = create_test_client()
    
    # Full preference data with new fields
    full_prefs = {
        "user_id": "test_user",
        "time_zone": "Europe/London",
        "working_hours": {
            "0": {"start": "08:00", "end": "16:00"},
            "1": {"start": "08:00", "end": "16:00"},
            "2": {"start": "08:00", "end": "16:00"},
            "3": {"start": "08:00", "end": "16:00"},
            "4": {"start": "08:00", "end": "15:00"}
        },
        "preferred_meeting_times": [
            {"start": "10:00", "end": "11:00"},
            {"start": "14:00", "end": "15:00"}
        ],
        "days_off": ["2024-12-25", "2024-12-26"],
        "preferred_break_duration_minutes": 20,
        "work_block_max_duration_minutes": 120,
        "preferred_activity_duration": {
            "WORK": 60,
            "PERSONAL": 30
        },
        "energy_levels": {
            "08:00-12:00": "HIGH",
            "14:00-16:00": "MEDIUM"
        },
        "social_preferences": {"preferred_meeting_days": ["tuesday", "thursday"]},
        "rest_preferences": {"lunch_time": "12:00-13:00"},
        "input_mode": "both",
        "voice_button_position": "left",
        "created_at": 1234567890,
        "updated_at": 1234567890
    }
    
    mock_get = Mock(return_value=full_prefs)
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    
    response = client.get("/preferences/test_user")
    assert response.status_code == 200
    
    response_data = response.json()
    assert response_data["input_mode"] == "both"
    assert response_data["voice_button_position"] == "left"
    assert response_data["time_zone"] == "Europe/London"
    assert response_data["preferred_break_duration_minutes"] == 20