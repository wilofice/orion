from tests.conftest import create_test_client

SAVED_PREFS = {
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
    "created_at": 1,
    "updated_at": 1,
}


def test_create_preferences(monkeypatch):
    client = create_test_client()

    get_call_results = [None, SAVED_PREFS]
    def mock_get(uid):
        return get_call_results.pop(0)
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", mock_get)
    monkeypatch.setattr("app.user_preferences_router.save_user_preferences", lambda prefs: "success")

    payload = {
        "user_id": "test_user",
        "time_zone": "UTC",
        "working_hours": {"monday": {"start": "09:00", "end": "17:00"}},
    }
    resp = client.post("/preferences/test_user", json=payload)
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "test_user"


def test_get_preferences(monkeypatch):
    client = create_test_client()
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", lambda uid: SAVED_PREFS)
    resp = client.get("/preferences/test_user")
    assert resp.status_code == 200
    assert resp.json()["user_id"] == "test_user"


def test_update_preferences(monkeypatch):
    client = create_test_client()
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", lambda uid: SAVED_PREFS)
    monkeypatch.setattr("app.user_preferences_router.update_user_preferences", lambda uid, updates: "success")
    resp = client.put("/preferences/test_user", json={"time_zone": "UTC"})
    assert resp.status_code == 200


def test_delete_preferences(monkeypatch):
    client = create_test_client()
    monkeypatch.setattr("app.user_preferences_router.get_user_preferences", lambda uid: SAVED_PREFS)
    monkeypatch.setattr("app.user_preferences_router.delete_user_preferences", lambda uid: True)
    resp = client.delete("/preferences/test_user")
    assert resp.status_code == 200

