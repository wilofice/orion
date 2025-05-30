import logging
from typing import List

from fastapi import APIRouter, HTTPException, Depends

from gemini_interface import ConversationTurn, ConversationRole
from dynamodb import get_user_conversations
from pydantic import BaseModel
from core.security import verify_token

router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


class Conversation(BaseModel):
    session_id: str
    user_id: str
    history: List[ConversationTurn]


@router.get("/{user_id}", response_model=List[Conversation])
async def list_user_conversations(
    user_id: str,
    current_user_id: str = Depends(verify_token)
):
    """Return all chat sessions for the given user."""    
    # Verify that the authenticated user can only access their own conversations
    if current_user_id != user_id:
        logging.warning(f"User {current_user_id} attempted to access conversations for user {user_id}")
        raise HTTPException(
            status_code=403,
            detail="You can only access your own conversations"
        )
    try:
        items = get_user_conversations(user_id)
        conversations = []
        for item in items:
            # Filter to only include USER and AI (MODEL) messages
            filtered_turns = []
            for turn in item.get("history", []):
                turn_obj = ConversationTurn(**turn)
                if turn_obj.role in [ConversationRole.USER, ConversationRole.MODEL]:
                    filtered_turns.append(turn_obj)
            
            conversations.append(
                Conversation(
                    session_id=item.get("session_id"),
                    user_id=item.get("user_id"),
                    history=filtered_turns,
                )
            )
        return conversations
    except Exception as exc:
        logging.exception("Failed to retrieve conversations")
        raise HTTPException(status_code=500, detail="Failed to retrieve conversations") from exc
