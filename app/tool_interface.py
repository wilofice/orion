# app/tool_interface.py

import logging
from datetime import time
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

from pydantic import BaseModel, Field, ConfigDict

from models import UserPreferences, DayOfWeek
    # Assuming calendar_client.py defines the abstract client interface
from calendar_client import AbstractCalendarClient
# Assuming gemini_interface.py defines FunctionCall
from gemini_interface import FunctionCall

# --- Enums ---

class ToolResultStatus(str, Enum):
    """Indicates the outcome of a tool execution."""
    SUCCESS = "success"
    ERROR = "error"
    CLARIFICATION_NEEDED = "clarification_needed"


# --- Data Structures (Task 5.2, 5.3) ---

class ExecutionContext(BaseModel):
    """
    Provides necessary context for executing a tool.
    Passed from the Orchestrator to the Tool Executor.
    """
    user_id: str = Field(..., description="The ID of the user requesting the action.")
    preferences: UserPreferences = Field(..., description="The user's preferences relevant to the tool.")
    # Use the abstract base class for type hinting to allow different implementations
    calendar_client: AbstractCalendarClient = Field(..., description="An initialized instance of a calendar client.")
    # Add other context if needed, e.g., access to WantToDo list, database connection
    model_config = ConfigDict(arbitrary_types_allowed=True)


class ExecutorToolResult(BaseModel):
    """
    Represents the result returned by the Tool Executor after attempting
    to execute a function call. This structure is used internally before
    potentially being formatted for Gemini history (see ToolResult in gemini_interface.py).
    """
    name: str = Field(..., description="The name of the function that was attempted.")
    status: ToolResultStatus = Field(..., description="The outcome status of the execution attempt.")
    # Flexible dictionary for successful results or structured error/clarification data
    result: Optional[Dict[str, Any]] = Field(None, description="Dictionary containing successful execution results (e.g., event details) or structured data for other statuses.")
    error_details: Optional[str] = Field(None, description="Detailed error message if status is 'error'.")
    clarification_prompt: Optional[str] = Field(None, description="Suggested prompt/question to ask the user if status is 'clarification_needed'.")

    class Config:
        # Allow arbitrary types for calendar_client (though AbstractCalendarClient is preferred)
        arbitrary_types_allowed = True


# --- Interface Function Signature (Conceptual - Task 5.1) ---
# This function would reside within the ToolExecutor module/class

# def execute_tool(
#     call: FunctionCall,
#     context: ExecutionContext
# ) -> ExecutorToolResult:
#     """
#     Executes the requested function call using the provided context.
#
#     Args:
#         call: The FunctionCall object parsed from the Gemini response.
#         context: The ExecutionContext containing user prefs, clients, etc.
#
#     Returns:
#         An ExecutorToolResult indicating the outcome.
#     """
#     logger = logging.getLogger(__name__)
#     logger.info(f"Executing tool: {call.name}")
#     # 1. Find the appropriate wrapper function based on call.name
#     # 2. Validate call.args against the function's expected parameters
#     # 3. Call the wrapper function with call.args and context
#     # 4. Handle exceptions from the wrapper
#     # 5. Format the wrapper's output into an ExecutorToolResult
#     pass # Placeholder


