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
from dynamodb import get_dynamodb_resource

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

default_session_history = [
            ConversationTurn(role=ConversationRole.SYSTEM,
                             parts=[f''' You are an advanced language model responsible for scheduling activities based on user preferences and calendar availability. When a user provides a prompt, you should intelligently infer and guess any missing parameters from the context provided by the user. Do not enforce the requirement for the user to specify every precise parameter. Instead, use your understanding to fill in the gaps and ensure the function call is complete and valid.
                                Your task is to create a calendar event based on the user's request. You will receive a function call with parameters such as event name, start time, end time, and any other relevant details. If the user does not specify all required parameters, you should infer and guess the missing values based on the context provided.
Current Date and Time : {datetime.now(ZoneInfo("Europe/Paris")).isoformat()}
Current zone info is : {ZoneInfo("Europe/Paris")}
Instructions: Assistant should follow these instructions:
Infer Missing Parameters: If the user does not specify all required parameters, use the context provided to infer and guess the missing values. Use the current date and time as a reference point. If the user said "tomorrow", use the next day from the current date for instance. If the user did not specify a time, use the current time as a reference and adjust accordingly. Guess the duration based on the context (e.g., if the user said "lunch", assume 1 hour).
Contextual Understanding: Leverage your understanding of natural language to fill in gaps and ensure the function call is complete.
Human-Centric Approach: Remember that users may not always provide precise details. Your role is to assist by making intelligent guesses to complete the scheduling task. For now, never ask the user for more clarification.
Response with Event Details: In the next turn, when the tool is executed successfully with the parameters you have provided, the created event details will be passed back to you by the program. Respond to the user in general language, including the event details and a link where the user can check the created event.
Suggest Next Activities: Make suggestions about possible next activities the user may want to pursue based on the context and the scheduled event.
MANDATORY: Do not ask the user for more clarification. Always infer and guess the missing parameters based on the context provided by the user. When prompted for the task, always respond with a function call that includes all necessary parameters, even if some are inferred. If the user does not specify a time, use the current time as a reference and adjust accordingly. If the user does not specify a duration, assume 1 hour by default.
                             '''],
                             timestamp=datetime.now(timezone.utc)-timedelta(minutes=3)),
        ]
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


# --- Example Usage ---
if __name__ == '__main__':
    import asyncio

    logging.basicConfig(level=logging.INFO)

    async def run_example():
        # In a real app, initialize with a connected DB client
        session_manager = MongoSessionManager() # Dummy instance

        user_id = "user_test_1"
        print("--- Creating Session ---")
        session_id = await session_manager.create_session(user_id)
        print(f"New session ID: {session_id}")

        print("\n--- Appending Turns ---")
        turn1 = ConversationTurn.user_turn("Schedule lunch for tomorrow")
        await session_manager.append_turn(session_id, turn1)

        # Simulate model response (function call)
        # Need FunctionCall model if using strict types
        class FunctionCall: name="find_time"; args={"duration": "1h"}
        turn2_content = FunctionCall()
        # turn2 = ConversationTurn.model_turn_function_call(turn2_content) # If using gemini_interface model
        turn2 = ConversationTurn(role=ConversationRole.MODEL, parts=[{"name": "find_time", "args": {"duration": "1h"}}])
        await session_manager.append_turn(session_id, turn2)

        print("\n--- Getting History ---")
        # Use a known dummy session ID for get_history example
        dummy_session = "existing_session_123"
        history = await session_manager.get_history(dummy_session)
        if history:
            print(f"History for session {dummy_session}:")
            for turn in history:
                print(f"- Role: {turn.role}, Content: {turn.parts}")
        else:
            print(f"No history found for session {dummy_session}")

        history_new = await session_manager.get_history(session_id)
        print(f"\nHistory for new session {session_id}: (Expected empty in dummy implementation)")
        print(history_new)

    asyncio.run(run_example())
