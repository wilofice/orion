# app/tool_interface.py

import logging
from datetime import time
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

from pydantic import BaseModel, Field, ConfigDict

# Attempt to import dependent models and interfaces
try:
    # Assuming models.py is accessible
    from models import UserPreferences, DayOfWeek
    # Assuming calendar_api.py defines the abstract client interface
    from calendar_api import AbstractCalendarClient
    # Assuming gemini_interface.py defines FunctionCall
    from gemini_interface import FunctionCall
except ImportError:
    # Fallback for running script directly or if structure differs
    print("Warning: Could not import dependent models/interfaces. Using dummy classes.")
    # Define dummy classes if needed for standalone testing

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


# --- Example Usage ---
if __name__ == '__main__':
    # Dummy context objects for example
    class DummyPrefs(UserPreferences):
        user_id: str = "user_123"
        time_zone: str = "UTC"
        working_hours: Dict[DayOfWeek, Tuple[time, time]] = {
            DayOfWeek.MONDAY: (time(9, 0), time(17, 0)),
            DayOfWeek.TUESDAY: (time(9, 0), time(17, 0)),
            DayOfWeek.WEDNESDAY: (time(9, 0), time(17, 0)),
            DayOfWeek.THURSDAY: (time(9, 0), time(17, 0)),
            DayOfWeek.FRIDAY: (time(9, 0), time(16, 0)),
        }
    class DummyClient(AbstractCalendarClient):
        def authenticate(self): pass
        def get_busy_slots(self, *args, **kwargs): return []
        def calculate_free_slots(self, *args, **kwargs): return []
        def get_available_time_slots(self, *args, **kwargs): return []

    exec_context = ExecutionContext(
        user_id="user_123",
        preferences=DummyPrefs(),
        calendar_client=DummyClient()
    )
    print("--- ExecutionContext Example ---")
    # Note: Pydantic might exclude calendar_client from default dict/json representation
    # if it doesn't have standard serializable fields.
    print(exec_context.model_dump(exclude={'calendar_client'})) # Exclude non-serializable field for print

    # Example Tool Results
    result_success = ExecutorToolResult(
        name="schedule_activity",
        status=ToolResultStatus.SUCCESS,
        result={"event_id": "evt_abc", "scheduled_time": "2025-05-02T10:00:00Z"}
    )
    result_error = ExecutorToolResult(
        name="schedule_activity",
        status=ToolResultStatus.ERROR,
        error_details="Could not find any available time slot matching the request."
    )
    result_clarify = ExecutorToolResult(
        name="schedule_activity",
        status=ToolResultStatus.CLARIFICATION_NEEDED,
        clarification_prompt="Which 'Project Meeting' did you mean? There are two scheduled.",
        result={"conflicting_meetings": ["id1", "id2"]} # Optional structured data
    )

    print("\n--- ExecutorToolResult Examples ---")
    print("Success:", result_success.model_dump_json(indent=2))
    print("Error:", result_error.model_dump_json(indent=2))
    print("Clarification:", result_clarify.model_dump_json(indent=2))

