import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional

from db import get_user_preferences as db_get_user_preferences
from models import (
    UserPreferences,
    DayOfWeek,
    EnergyLevel,
    InputMode,
    VoiceButtonPosition,
    ActivityCategory,
)

logger = logging.getLogger(__name__)


async def get_user_preferences(user_id: str) -> UserPreferences:
    """Retrieve and parse stored user preferences."""

    def fetch() -> Optional[Dict[str, Any]]:
        return db_get_user_preferences(user_id)

    prefs_dict = await asyncio.to_thread(fetch)
    if not prefs_dict:
        return UserPreferences(user_id=user_id)

    try:
        working_hours: Dict[DayOfWeek, tuple] = {}
        for key, hours in prefs_dict.get("working_hours", {}).items():
            try:
                day = DayOfWeek[int(key.split(".")[-1])]
            except ValueError:
                day = DayOfWeek(int(key))
            start = datetime.strptime(hours["start"], "%H:%M").time()
            end = datetime.strptime(hours["end"], "%H:%M").time()
            working_hours[day] = (start, end)

        meeting_times = [
            (
                datetime.strptime(t["start"], "%H:%M").time(),
                datetime.strptime(t["end"], "%H:%M").time(),
            )
            for t in prefs_dict.get("preferred_meeting_times", [])
        ]

        days_off = [date.fromisoformat(d) for d in prefs_dict.get("days_off", [])]

        activity = {
            ActivityCategory(k): timedelta(minutes=v)
            for k, v in prefs_dict.get("preferred_activity_duration", {}).items()
        }

        energy = {}
        for k, level in prefs_dict.get("energy_levels", {}).items():
            start_s, end_s = k.split("-")
            energy[
                (
                    datetime.strptime(start_s, "%H:%M").time(),
                    datetime.strptime(end_s, "%H:%M").time(),
                )
            ] = EnergyLevel(level)

        return UserPreferences(
            user_id=user_id,
            time_zone=prefs_dict.get("time_zone", "UTC"),
            working_hours=working_hours or None,
            preferred_meeting_times=meeting_times,
            days_off=days_off,
            preferred_break_duration=timedelta(
                minutes=prefs_dict.get("preferred_break_duration_minutes", 15)
            ),
            work_block_max_duration=timedelta(
                minutes=prefs_dict.get("work_block_max_duration_minutes", 90)
            ),
            preferred_activity_duration=activity,
            energy_levels=energy,
            social_preferences=prefs_dict.get("social_preferences", {}),
            rest_preferences=prefs_dict.get("rest_preferences", {}),
            input_mode=InputMode(prefs_dict.get("input_mode", "text")),
            voice_button_position=VoiceButtonPosition(
                prefs_dict.get("voice_button_position", "right")
            ),
        )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to parse stored user preferences, using defaults")
        return UserPreferences(user_id=user_id)
