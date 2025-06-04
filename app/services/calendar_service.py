import logging
from fastapi import HTTPException, status
from typing import Any

from ..calendar_client import AbstractCalendarClient, GoogleCalendarAPIClient
from ..db import get_decrypted_user_tokens
from ..settings_v1 import settings

logger = logging.getLogger(__name__)

def get_calendar_client_for_user(user_id: str) -> AbstractCalendarClient:
    """Return a calendar client instance for the given user.

    The implementation is selected based on the CALENDAR_PROVIDER setting. Only
    the Google provider is currently supported but the function is structured so
    new providers can be added easily in the future.
    """
    provider = getattr(settings, "CALENDAR_PROVIDER", "google").lower()

    if provider == "google":
        tokens = get_decrypted_user_tokens(user_id)
        if not tokens or "access_token" not in tokens:
            logger.error("No valid tokens found for user %s", user_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User tokens not found or invalid. Please reconnect calendar.",
            )
        return GoogleCalendarAPIClient(token_info=tokens)

    logger.error("Unsupported calendar provider: %s", provider)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Calendar provider '{provider}' not supported",
    )
