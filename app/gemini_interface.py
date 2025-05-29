# app/gemini_interface.py

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any, Union

from pydantic import BaseModel, Field

# --- Enums ---

class ResponseType(str, Enum):
    """Indicates the type of response received from Gemini."""
    TEXT = "text"
    FUNCTION_CALL = "function_call"
    ERROR = "error"

class ConversationRole(str, Enum):
    """Indicates the originator of a message in the conversation history."""
    USER = "USER"
    SYSTEM = "SYSTEM"  # Optional, for system messages or instructions
    MODEL = "AI"
    # Represents the result of a function call requested by the model
    FUNCTION = "FUNCTION" # Changed from TOOL to match Gemini API

class ToolResultStatus(str, Enum):
    """Indicates the outcome of a tool execution."""
    SUCCESS = "success"
    ERROR = "error"
    CLARIFICATION_NEEDED = "clarification_needed"



class FunctionCall(BaseModel):
    """Represents a function call requested by the Gemini model."""
    name: str = Field(..., description="The name of the function to call.")
    # Arguments are provided by Gemini as a dictionary
    args: Dict[str, Any] = Field(..., description="The arguments to pass to the function, as provided by the model.")


class ToolResult(BaseModel):
    """Represents the result of executing a tool (function call)."""
    # Corresponds to FunctionResponse part in Gemini API
    name: str = Field(..., description="The name of the function that was called.")
    # The actual data returned by the function execution
    response: Dict[str, Any] = Field(
        ...,
        description="The result of the function execution, structured as a dictionary."
                    " Should contain keys like 'status', 'message', 'result_data', etc."
                    " Needs to be serializable (e.g., JSON)."
    )
    # --- Internal Status Tracking (Optional - may not be sent back to Gemini directly) ---
    # status: ToolResultStatus = Field(..., description="Internal status indicating tool execution outcome.")
    # message: Optional[str] = Field(None, description="Optional message accompanying the status (e.g., error details).")


# Content part of a ConversationTurn
# Model can return text or a function call request
# User always provides text
# Function role provides the result of a function execution
ContentData = Union[str, FunctionCall, ToolResult]

class ConversationTurn(BaseModel):
    """Represents a single turn in the conversation history."""
    role: ConversationRole = Field(..., description="The role of the entity providing the content (user, model, or function).")
    # Using 'parts' to align with Gemini API structure which expects a list
    parts: List[ContentData] = Field(..., description="The content of the turn. Usually a list containing a single item (text, function call, or function response).")

    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc), description="Optional timestamp of when the turn occurred. Can be used for logging or debugging.")
    # Helper validator/constructor for convenience (optional)
    @classmethod
    def user_turn(cls, text: str) -> 'ConversationTurn':
        return cls(role=ConversationRole.USER, parts=[f"USER: {text}"])

    @classmethod
    def model_turn_text(cls, text: str) -> 'ConversationTurn':
        return cls(role=ConversationRole.MODEL, parts=[f"AI: {text}"])

    @classmethod
    def model_turn_function_call(cls, function_call: FunctionCall) -> 'ConversationTurn':
        return cls(role=ConversationRole.MODEL, parts=[f"AI FUNCTION CALL: {function_call.model_dump_json()}"])

    @classmethod
    def function_turn(cls, tool_result: ToolResult) -> 'ConversationTurn':
        return cls(role=ConversationRole.FUNCTION, parts=[f"FUNCTION RESULT: {tool_result.model_dump_json()}"])


# Placeholder for ToolDefinition - should match Gemini API's FunctionDeclaration
# Using Dict for simplicity here, but in practice, load/define the actual schema.
# See: https://ai.google.dev/api/python/google/ai/generativelanguage/FunctionDeclaration
ToolDefinition = Dict[str, Any]


class GeminiRequest(BaseModel):
    """Data structure for sending a request to the Gemini Client."""
    # The user's latest prompt is usually the last item in history
    # prompt: str = Field(..., description="The user's current prompt text.") # Often redundant if history is managed correctly
    history: List[ConversationTurn] = Field(..., description="The conversation history including previous turns.")
    tools: Optional[List[ToolDefinition]] = Field(None, description="List of tool definitions (FunctionDeclarations) available for the model to call.")
    # max_output_tokens: Optional[int] = Field(None, description="Optional maximum number of tokens to generate.") # Control via GenerationConfig usually
    # Add other parameters like GenerationConfig if needed


class GeminiResponse(BaseModel):
    """Data structure representing the response from the Gemini Client."""
    response_type: ResponseType = Field(..., description="The type of response received.")
    text: Optional[str] = Field(None, description="The text content of the response, if type is TEXT.")
    function_call: Optional[FunctionCall] = Field(None, description="The function call details, if type is FUNCTION_CALL.")
    error_message: Optional[str] = Field(None, description="Error details, if type is ERROR.")
    # Optionally include the full conversation history up to this point
    # full_history: Optional[List[ConversationTurn]] = Field(None)


# --- Interface Function Signature (Conceptual - Task 4.1) ---
# This function would reside within the GeminiClient module/class

# def send_to_gemini(request: GeminiRequest) -> GeminiResponse:
#     """
#     Sends the request to the Gemini API and processes the response.
#     (Actual implementation would use the google.generativeai library)
#     """
#     logger = logging.getLogger(__name__)
#     logger.info("Sending request to Gemini...")
#     # ... implementation using google.generativeai library ...
#     # response = model.generate_content(..., tools=request.tools, history=...)
#     # ... parse response into GeminiResponse object ...
#     pass # Placeholder


# --- Example Usage ---
if __name__ == '__main__':
    # Example Function Call object
    fc = FunctionCall(name="schedule_activity", args={"title": "Team Lunch", "date_str": "tomorrow 12pm", "duration_minutes": 60})
    print("--- FunctionCall Example ---")
    print(fc.model_dump_json(indent=2))

    # Example ToolResult object
    tr = ToolResult(
        name="schedule_activity",
        response={
            "status": "SUCCESS",
            "message": "Event scheduled successfully.",
            "event_id": "evt_123xyz",
            "scheduled_start": "2025-05-02T12:00:00+02:00",
            "scheduled_end": "2025-05-02T13:00:00+02:00"
        }
    )
    print("\n--- ToolResult Example ---")
    print(tr.model_dump_json(indent=2))

    # Example Conversation Turns
    turn1 = ConversationTurn.user_turn("Schedule team lunch tomorrow at 12pm for an hour")
    turn2 = ConversationTurn.model_turn_function_call(fc)
    turn3 = ConversationTurn.function_turn(tr)
    turn4 = ConversationTurn.model_turn_text("OK. I've scheduled 'Team Lunch' for tomorrow from 12:00 PM to 1:00 PM.")

    print("\n--- ConversationTurn Examples ---")
    print(turn1.model_dump_json(indent=2))
    print(turn2.model_dump_json(indent=2))
    print(turn3.model_dump_json(indent=2))
    print(turn4.model_dump_json(indent=2))

    # Example GeminiRequest
    req = GeminiRequest(
        history=[turn1, turn2, turn3], # History up to the point where model needs to generate final text
        tools=[{ # Placeholder ToolDefinition
            "name": "schedule_activity",
            "description": "Schedules an event.",
            "parameters": {"type": "object", "properties": {}} # Simplified
        }]
    )
    print("\n--- GeminiRequest Example ---")
    print(req.model_dump_json(indent=2))

    # Example GeminiResponse (Text)
    resp_text = GeminiResponse(response_type=ResponseType.TEXT, text="OK. I've scheduled 'Team Lunch' for tomorrow from 12:00 PM to 1:00 PM.")
    print("\n--- GeminiResponse (Text) Example ---")
    print(resp_text.model_dump_json(indent=2))

    # Example GeminiResponse (Function Call)
    resp_fc = GeminiResponse(response_type=ResponseType.FUNCTION_CALL, function_call=fc)
    print("\n--- GeminiResponse (Function Call) Example ---")
    print(resp_fc.model_dump_json(indent=2))

    # Example GeminiResponse (Error)
    resp_err = GeminiResponse(response_type=ResponseType.ERROR, error_message="API authentication failed.")
    print("\n--- GeminiResponse (Error) Example ---")
    print(resp_err.model_dump_json(indent=2))

