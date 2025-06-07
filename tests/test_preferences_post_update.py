"""Tests for POST method update functionality in user preferences."""
import pytest
from unittest.mock import Mock, call
from tests.conftest import create_test_client


def test_post_creates_new_preferences_when_none_exist(monkeypatch):
    """Test that POST creates new preferences when none exist."""
    client = create_test_client()
    
    # Mock no existing preferences
    mock_get = Mock(return_value=None)
    mock_save = Mock(return_value="success")
    mock_get_after_save = Mock(return_value={
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {"0": {"start": "09:00", "end": "17:00"}},
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
    
    # Set up mocks to return None first (no existing), then the saved preferences
    get_calls = [mock_get, mock_get_after_save]
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", 
                       lambda user_id: get_calls.pop(0)(user_id))
    monkeypatch.setattr("app.user_preferences_router.save_user_preferences", mock_save)
    
    request_data = {
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {
            "monday": {"start": "09:00", "end": "17:00"}
        }
    }
    
    response = client.post("/preferences/test_user", json=request_data)
    assert response.status_code == 200
    assert response.json()["user_id"] == "test_user"
    
    # Verify save was called
    mock_save.assert_called_once()


def test_post_replaces_existing_preferences(monkeypatch):
    """Test that POST replaces existing preferences when they already exist."""
    client = create_test_client()
    
    # Mock existing preferences
    existing_prefs = {
        "user_id": "test_user",
        "time_zone": "America/New_York",
        "working_hours": {"0": {"start": "08:00", "end": "16:00"}},
        "input_mode": "voice",
        "voice_button_position": "left"
    }
    
    # Mock new preferences after replacement
    new_prefs = {
        "user_id": "test_user",
        "time_zone": "Europe/London",
        "working_hours": {"0": {"start": "09:00", "end": "17:00"}},
        "preferred_meeting_times": [],
        "days_off": [],
        "preferred_break_duration_minutes": 20,
        "work_block_max_duration_minutes": 120,
        "preferred_activity_duration": {},
        "energy_levels": {},
        "social_preferences": {},
        "rest_preferences": {},
        "input_mode": "both",
        "voice_button_position": "right",
        "created_at": 1234567890,
        "updated_at": 1234567891
    }
    
    # Mock functions
    mock_delete = Mock(return_value=True)
    mock_save = Mock(return_value="success")
    
    # Set up get_user_preferences to return existing first, then new after save
    get_calls = [Mock(return_value=existing_prefs), Mock(return_value=new_prefs)]
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", 
                       lambda user_id: get_calls.pop(0)(user_id))
    monkeypatch.setattr("app.user_preferences_router.delete_user_preferences", mock_delete)
    monkeypatch.setattr("app.user_preferences_router.save_user_preferences", mock_save)
    
    request_data = {
        "user_id": "test_user",
        "time_zone": "Europe/London",
        "working_hours": {
            "monday": {"start": "09:00", "end": "17:00"}
        },
        "preferred_break_duration_minutes": 20,
        "work_block_max_duration_minutes": 120,
        "input_mode": "both",
        "voice_button_position": "right"
    }
    
    response = client.post("/preferences/test_user", json=request_data)
    assert response.status_code == 200
    
    # Verify old preferences were deleted
    mock_delete.assert_called_once_with("test_user")
    
    # Verify new preferences were saved
    mock_save.assert_called_once()
    
    # Verify response contains new preferences
    response_data = response.json()
    assert response_data["time_zone"] == "Europe/London"
    assert response_data["input_mode"] == "both"
    assert response_data["voice_button_position"] == "right"
    assert response_data["preferred_break_duration_minutes"] == 20


def test_post_handles_delete_failure_when_replacing(monkeypatch):
    """Test that POST handles failure when trying to delete existing preferences."""
    client = create_test_client()
    
    # Mock existing preferences
    existing_prefs = {"user_id": "test_user", "time_zone": "UTC"}
    
    # Mock delete failure
    mock_get = Mock(return_value=existing_prefs)
    mock_delete = Mock(return_value=False)  # Deletion fails
    
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    monkeypatch.setattr("app.user_preferences_router.delete_user_preferences", mock_delete)
    
    request_data = {
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {
            "monday": {"start": "09:00", "end": "17:00"}
        }
    }
    
    response = client.post("/preferences/test_user", json=request_data)
    assert response.status_code == 500
    assert "Failed to replace existing preferences" in response.json()["detail"]


def test_post_validates_user_id_matches(monkeypatch):
    """Test that POST validates user_id in path matches request body."""
    client = create_test_client()
    
    # Mock no existing preferences
    mock_get = Mock(return_value=None)
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    
    request_data = {
        "user_id": "different_user",  # Different from path
        "time_zone": "UTC",
        "working_hours": {
            "monday": {"start": "09:00", "end": "17:00"}
        }
    }
    
    response = client.post("/preferences/test_user", json=request_data)
    assert response.status_code == 400
    assert "User ID in path does not match" in response.json()["detail"]


def test_post_enforces_user_can_only_create_own_preferences(monkeypatch):
    """Test that POST enforces users can only create their own preferences."""
    # Create client with different authenticated user
    client = create_test_client(verify_user_id="other_user")
    
    request_data = {
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {
            "monday": {"start": "09:00", "end": "17:00"}
        }
    }
    
    response = client.post("/preferences/test_user", json=request_data)
    assert response.status_code == 403
    assert "You can only create your own preferences" in response.json()["detail"]


def test_post_completely_replaces_preferences_not_merge(monkeypatch):
    """Test that POST completely replaces preferences, doesn't merge."""
    client = create_test_client()
    
    # Mock existing preferences with many fields
    existing_prefs = {
        "user_id": "test_user",
        "time_zone": "America/New_York",
        "working_hours": {
            "0": {"start": "08:00", "end": "16:00"},
            "1": {"start": "08:00", "end": "16:00"},
            "2": {"start": "08:00", "end": "16:00"}
        },
        "preferred_meeting_times": [
            {"start": "10:00", "end": "11:00"},
            {"start": "14:00", "end": "15:00"}
        ],
        "days_off": ["2024-12-25", "2024-12-26"],
        "input_mode": "voice",
        "voice_button_position": "left"
    }
    
    # New preferences with minimal fields
    new_prefs = {
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {"0": {"start": "09:00", "end": "17:00"}},
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
        "updated_at": 1234567891
    }
    
    # Mock functions
    mock_delete = Mock(return_value=True)
    mock_save = Mock(return_value="success")
    
    # Set up get_user_preferences
    get_calls = [Mock(return_value=existing_prefs), Mock(return_value=new_prefs)]
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", 
                       lambda user_id: get_calls.pop(0)(user_id))
    monkeypatch.setattr("app.user_preferences_router.delete_user_preferences", mock_delete)
    monkeypatch.setattr("app.user_preferences_router.save_user_preferences", mock_save)
    
    # Request with minimal data
    request_data = {
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {
            "monday": {"start": "09:00", "end": "17:00"}
        }
    }
    
    response = client.post("/preferences/test_user", json=request_data)
    assert response.status_code == 200
    
    # Verify response doesn't contain old data
    response_data = response.json()
    assert response_data["time_zone"] == "UTC"
    assert len(response_data["working_hours"]) == 1  # Only monday
    assert response_data["working_hours"]["monday"]["start"] == "09:00"
    assert len(response_data["preferred_meeting_times"]) == 0  # Empty, not the old values
    assert len(response_data["days_off"]) == 0  # Empty, not the old values
    assert response_data["input_mode"] == "text"  # Default, not old "voice"
    assert response_data["voice_button_position"] == "right"  # Default, not old "left"