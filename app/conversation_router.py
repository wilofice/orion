import logging
from typing import List

from fastapi import APIRouter, HTTPException

from gemini_interface import ConversationTurn
from dynamodb import get_user_conversations
from pydantic import BaseModel

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


class Conversation(BaseModel):
    session_id: str
    user_id: str
    history: List[ConversationTurn]


@router.get("/{user_id}", response_model=List[Conversation])
async def list_user_conversations(user_id: str):
    """Return all chat sessions for the given user."""
    try:
        items = get_user_conversations(user_id)
        conversations = []
        for item in items:
            turns = [ConversationTurn(**turn) for turn in item.get("history", [])]
            conversations.append(
                Conversation(
                    session_id=item.get("session_id"),
                    user_id=item.get("user_id"),
                    history=turns,
                )
            )
        return conversations
    except Exception as exc:
        logging.exception("Failed to retrieve conversations")
        raise HTTPException(status_code=500, detail="Failed to retrieve conversations") from exc
