# app/session_manager.py

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
import uuid
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
# Assuming pymongo or motor is used for MongoDB interaction
# from pymongo.database import Database
# from motor.motor_asyncio import AsyncIOMotorDatabase

# Attempt to import ConversationTurn from gemini_interface
from gemini_interface import ConversationTurn, ConversationRole
from settings_v1 import settings
from db import get_dynamodb_resource

logger = logging.getLogger(__name__)

# --- MongoDB Document Structure (Conceptual) ---
# Collection Name: chat_sessions
#
# {
#   "_id": "<session_id>",          # String (UUID recommended) - Primary Key
#   "user_id": "<user_id>",          # String - Indexed
#   "created_at": ISODate("..."),    # DateTime - Indexed
#   "last_updated_at": ISODate("..."), # DateTime - Indexed, TTL Index Applied
#   "history": [                     # Array of ConversationTurn objects (or dicts)
#     {
#       "role": "user|model|function", # String (Enum value)
#       "parts": [                   # List containing the content part(s)
#         # e.g., "User prompt text"
#         # e.g., {"name": "func_name", "args": {...}}
#         # e.g., {"name": "func_name", "response": {...}}
#       ],
#       "timestamp": ISODate("...") # Timestamp for the turn
#     },
#     # ... more turns
#   ]
# }
#
# --- MongoDB Indexes ---
# 1. Primary Key: _id (automatically created)
# 2. Index on user_id (for querying user sessions)
# 3. Index on created_at (optional, for sorting or analytics)
# 4. TTL Index on last_updated_at (for automatic session expiration)
#    Example (pymongo):
#    db.chat_sessions.create_index(
#        "last_updated_at", expireAfterSeconds=24 * 60 * 60 # 24 hours
#    )


# --- Abstract Base Class for Session Management ---

class AbstractSessionManager(ABC):
    """Defines the interface for managing conversation session history."""

    @abstractmethod
    async def get_history(self, session_id: str) -> List[ConversationTurn]:
        """
        Retrieves the conversation history for a given session ID.

        Args:
            session_id: The unique identifier for the session.

        Returns:
            A list of ConversationTurn objects, ordered chronologically.
            Returns an empty list if the session is not found.
        """
        pass

    @abstractmethod
    async def append_turn(self, session_id: str, turn: ConversationTurn):
        """
        Appends a new turn to the conversation history of a session.
        Updates the session's last_updated_at timestamp.
        If the session doesn't exist, it should ideally be created first
        (or handle this case gracefully, perhaps requiring create_session).

        Args:
            session_id: The unique identifier for the session.
            turn: The ConversationTurn object to append.
        """
        pass

    @abstractmethod
    async def create_session(self, user_id: str, session_id: str) -> str:
        """
        Creates a new chat session for a user.

        Args:
            user_id: The ID of the user starting the session.

        Returns:
            The unique session_id generated for the new session.
        """
        pass

# --- MongoDB Implementation (Interface Definition) ---

default_session_history = []
class DynamoSessionManager(AbstractSessionManager):
    """Session manager implementation backed by DynamoDB."""

    def __init__(self):
        self.table = get_dynamodb_resource().Table(
            settings.DYNAMODB_CHAT_SESSIONS_TABLE_NAME
        )

    async def create_session(self, user_id: str, session_id: str) -> str:
        now = int(datetime.now(timezone.utc).timestamp())
        item = {"session_id": session_id, "user_id": user_id, "created_at": now, "last_updated_at": now,
                "history": [turn.model_dump(mode="json") for turn in default_session_history]}
        self.table.put_item(Item=item)
        return session_id

    async def append_turn(self, session_id: str, turn: ConversationTurn):
        if not turn.timestamp:
            turn.timestamp = datetime.now(timezone.utc)
        turn_dict = turn.model_dump(mode="json")
        try:
            response = self.table.update_item(
                Key={"session_id": session_id},
                UpdateExpression=(
                    "SET history = list_append(if_not_exists(history, :empty), :turn), "
                    "last_updated_at = :updated, "
                    "user_id = if_not_exists(user_id, :user_id), "
                    "created_at = if_not_exists(created_at, :created_at)"
                ),
                ExpressionAttributeValues={
                    ":turn": [turn_dict],
                    ":updated": int(turn.timestamp.timestamp()),
                    ":empty": [],
                    ":user_id": "unknown",  # Default value if user_id is missing
                    ":created_at": 0,  # Default value if created_at is missing
                },
                ReturnValues="UPDATED_NEW",  # Optional: Returns the updated attributes
            )
            # Log the response for debugging
            logger.info(f"Successfully updated session {session_id}: {response}")
        except Exception as e:
            logger.error(f"Failed to append turn to session {session_id}: {e}")
            raise

    async def get_history(self, session_id: str) -> List[ConversationTurn]:
        response = self.table.get_item(Key={"session_id": session_id})
        item = response.get("Item")
        if not item:
            return []
        history_data = item.get("history", [])
        return [ConversationTurn(**d) for d in history_data]


