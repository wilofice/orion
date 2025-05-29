import logging
import uuid
from datetime import time, timedelta, date
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
import json
from pydantic import BaseModel, Field
# --- Interface Imports ---
# Assuming interfaces and models from previous tasks are defined and importable
    # From Task ORCH-3 / main.py
from models import ChatRequest, ChatResponse, ResponseStatus, ErrorDetail, DayOfWeek, \
    EnergyLevel  # Or wherever these are defined
# From Task ORCH-4 / gemini_interface.py
from gemini_interface import (GeminiRequest, GeminiResponse, ConversationTurn,
                               ToolDefinition, ResponseType, FunctionCall, ToolResult,
                               ConversationRole)
# From Task ORCH-5 / tool_interface.py
from tool_interface import ExecutionContext, ExecutorToolResult, ToolResultStatus
# From Task ORCH-7 / session_manager.py
from session_manager import AbstractSessionManager
# From Task ORCH-6 / tool_wrappers.py (for TOOL_REGISTRY concept)
# from .tool_wrappers import TOOL_REGISTRY # Conceptual import
# From models.py (Task 1)
from models import UserPreferences
# From calendar_client.py (Task 2)
from calendar_client import AbstractCalendarClient
import threading
from settings_v1 import settings

class GenAIClientSingleton:
    _instance = None
    _lock = threading.Lock()  # Ensures thread safety

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:  # Double-checked locking
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize(*args, **kwargs)
        return cls._instance

    def _initialize(self, *args, **kwargs):
        # Initialize the GenAI client here
        self.client = self._create_genai_client(*args, **kwargs)

    def _create_genai_client(self, *args, **kwargs):
        # Replace with actual GenAI client initialization logic
        client = genai.Client(api_key=settings.GEMINI_API_KEY)  # Use settings or config for API key
        return client

    @staticmethod
    def get_instance(*args, **kwargs):
        return GenAIClientSingleton(*args, **kwargs).client

# --- Placeholder Interfaces/Implementations ---
# Define dummy classes if real ones aren't available yet
class AbstractGeminiClient:
    async def send_to_gemini(self, request: GeminiRequest) -> GeminiResponse:
        logger.info("Sending request to Gemini API...")

        # Prepare the tools for the request
        # tools = [
        #     {
        #         "name": tool.name,
        #         "description": tool.description,
        #         "parameters": tool.parameters,
        #     }
        #     for tool in request.tools
        # ]

        # Configure the request payload

        tools = types.Tool(function_declarations=request.tools)
        config = types.GenerateContentConfig(tools=[tools])
        payload = {
            "model": "gemini-2.0-flash",
            "contents": [turn.parts[0] for turn in request.history],
            "config": config,
        }

        try:
            # Call the Gemini API
            client = GenAIClientSingleton.get_instance()  # Replace with actual API key
            response = client.models.generate_content(**payload)

            # Parse the response
            if response.candidates[0].content.parts[0].function_call:
                function_call = response.candidates[0].content.parts[0].function_call
                logger.info(f"Received FUNCTION_CALL response: {function_call.name}")
                return GeminiResponse(
                    response_type=ResponseType.FUNCTION_CALL,
                    function_call=FunctionCall(
                        name=function_call.name,
                        args=function_call.args,
                    ),
                )
            elif response.candidates[0].content.parts[0].text:
                text = response.candidates[0].content.parts[0].text
                logger.info("Received TEXT response.")
                return GeminiResponse(
                    response_type=ResponseType.TEXT,
                    text=text,
                )
            else:
                logger.error("Unexpected response format from Gemini API.")
                return GeminiResponse(
                    response_type=ResponseType.ERROR,
                    error_message="Unexpected response format from Gemini API.",
                )

        except Exception as e:
            logger.exception("Error while communicating with Gemini API.")
            return GeminiResponse(
                response_type=ResponseType.ERROR,
                error_message=str(e),
            )

class AbstractToolExecutor:
    def execute_tool(self, call: FunctionCall, context: ExecutionContext) -> ExecutorToolResult:
        """
        Executes the requested function call using the provided context.

        Args:
            call: The FunctionCall object parsed from the Gemini response.
            context: The ExecutionContext containing user prefs, clients, etc.

        Returns:
            An ExecutorToolResult indicating the outcome.
        """
        logger = logging.getLogger(__name__)
        logger.info(f"Executing tool: {call.name}")

        # Step 1: Find the appropriate tool wrapper
        tool_wrapper = TOOL_REGISTRY.get(call.name)
        if not tool_wrapper:
            logger.error(f"Tool '{call.name}' not found in TOOL_REGISTRY.")
            return ExecutorToolResult(
                name=call.name,
                status=ToolResultStatus.ERROR,
                error_details=f"Tool '{call.name}' not found."
            )

        try:
            # Step 3: Call the wrapper function with call.args and context
            return tool_wrapper.run(call.args, context)
        except Exception as e:
            logger.exception(f"Error while executing tool '{call.name}': {e}")
            return ExecutorToolResult(
                name=call.name,
                status=ToolResultStatus.ERROR,
                error_details=f"An error occurred while executing tool '{call.name}': {str(e)}"
            )

class DummyPrefs(UserPreferences):
    user_id: str = Field(..., description="User ID")
    time_zone: str = Field(default="Europe/Paris", description="Time zone")
    working_hours: Dict[DayOfWeek, tuple] = Field(
        default={
            DayOfWeek.MONDAY: (time(9, 0), time(17, 0)),
            DayOfWeek.TUESDAY: (time(9, 0), time(17, 0)),
            DayOfWeek.WEDNESDAY: (time(9, 0), time(17, 0)),
            DayOfWeek.THURSDAY: (time(9, 0), time(17, 0)),
            DayOfWeek.FRIDAY: (time(9, 0), time(16, 0)),
        },
        description="Working hours for each day"
    )
    days_off: List[date] = Field(default=[date(2025, 1, 1)], description="Days off")
    preferred_break_duration: timedelta = Field(
        default=timedelta(minutes=5), description="Preferred break duration"
    )
    work_block_max_duration: timedelta = Field(
        default=timedelta(hours=2), description="Maximum work block duration"
    )
    energy_levels: Dict[tuple, EnergyLevel] = Field(
        default={
            (time(9, 0), time(12, 0)): EnergyLevel.HIGH,
            (time(13, 0), time(17, 0)): EnergyLevel.MEDIUM,
        },
        description="Energy levels throughout the day"
    )
    rest_preferences: Dict[str, tuple] = Field(
        default={"sleep_schedule": (time(23, 59), time(5, 0))},
        description="Rest preferences"
    )

# Dummy function to get preferences (replace with real implementation)
async def get_user_preferences(user_id: str) -> UserPreferences:
    logger.warning(f"Using DUMMY UserPreferences for user {user_id}")
    # Need a minimal UserPreferences object that passes validation if used

    return DummyPrefs(user_id=user_id)

# Tool Registry
from tool_wrappers import TOOL_REGISTRY

TOOL_DEFINITIONS: List[ToolDefinition] = [
    {
        "name": tool_name,
        "description": tool_wrapper.description,
        "parameters": tool_wrapper.parameters_schema,
    }
    for tool_name, tool_wrapper in TOOL_REGISTRY.items()
]

logger = logging.getLogger(__name__)

# Configuration
MAX_GEMINI_TURNS = 2 # Limit LLM calls per user prompt (User -> LLM -> Tool -> LLM -> User)

async def handle_chat_request(
    request: ChatRequest,
    session_manager: AbstractSessionManager,
    gemini_client: AbstractGeminiClient,
    tool_executor: AbstractToolExecutor,
    calendar_client: AbstractCalendarClient # Needed for ExecutionContext
) -> ChatResponse:
    """
    Core orchestration logic to handle a user chat request.

    Args:
        request: The incoming ChatRequest object.
        session_manager: Instance to manage conversation history.
        gemini_client: Instance to interact with the Gemini API.
        tool_executor: Instance to execute tool function calls.
        calendar_client: Instance of a calendar client for context.

    Returns:
        A ChatResponse object for the UI.
    """
    session_id = request.session_id or str(uuid.uuid4())
    user_id = request.user_id
    prompt_text = request.prompt_text
    turn_limit = MAX_GEMINI_TURNS
    current_turn = 0

    try:
        # 8.1 Authentication: Assumed done by FastAPI dependency before calling this handler.

        # 8.2 Load history and context
        logger.info(f"[Session: {session_id}] Loading history and context for user {user_id}")
        history: List[ConversationTurn] = await session_manager.get_history(session_id)
        if history == None or len(history) == 0 : # Check if session ID was provided but not found
             logger.warning(f"[Session: {session_id}] Provided session ID not found, starting new history.")
             # Optionally create session explicitly if needed by append_turn implementation
             await session_manager.create_session(user_id, session_id) # If create takes session_id
             history = await session_manager.get_history(session_id)

        preferences = await get_user_preferences(user_id) # Task ORCH-9 (using dummy here)

        # Append current user prompt to history
        user_turn = ConversationTurn.user_turn(prompt_text)
        history.append(user_turn)
        await session_manager.append_turn(session_id, user_turn) # Persist user turn

        # 8.3 Get available tools (replace DUMMY with actual registry access)
        available_tools = TOOL_DEFINITIONS # Task ORCH-7

        while current_turn < turn_limit:
            current_turn += 1
            logger.info(f"[Session: {session_id}] Gemini Turn {current_turn}/{turn_limit}")

            # 8.4 Build request and send to Gemini
            gemini_request = GeminiRequest(history=history, tools=available_tools)
            gemini_response = await gemini_client.send_to_gemini(gemini_request)

            # 8.5 Handle TEXT response
            if gemini_response.response_type == ResponseType.TEXT:
                logger.info(f"[Session: {session_id}] Received TEXT response from Gemini.")
                model_turn = ConversationTurn.model_turn_text(gemini_response.text)
                history.append(model_turn)
                await session_manager.append_turn(session_id, model_turn) # Persist model turn
                return ChatResponse(
                    session_id=session_id,
                    status=ResponseStatus.COMPLETED,
                    response_text=gemini_response.text
                )

            # 8.6 Handle FUNCTION_CALL response
            elif gemini_response.response_type == ResponseType.FUNCTION_CALL:
                logger.info(f"[Session: {session_id}] Received FUNCTION_CALL response from Gemini: {gemini_response.function_call.name}")
                # Append model's function call request to history
                model_fc_turn = ConversationTurn.model_turn_function_call(gemini_response.function_call)
                history.append(model_fc_turn)
                await session_manager.append_turn(session_id, model_fc_turn) # Persist model turn

                # 8.6.1 Execute the tool
                exec_context = ExecutionContext(
                    user_id=user_id,
                    preferences=preferences,
                    calendar_client=calendar_client
                )
                tool_exec_result: ExecutorToolResult = tool_executor.execute_tool(
                    call=gemini_response.function_call,
                    context=exec_context
                )
                logger.info(f"[Session: {session_id}] Tool execution result: {tool_exec_result.status}")

                # 8.6.2 Format tool result for Gemini history
                # Convert ExecutorToolResult into the ToolResult structure expected by Gemini API history
                # The 'response' dict should contain the data Gemini needs to formulate its final text response.
                gemini_tool_result_payload = {
                    "status": tool_exec_result.status.value,
                }

                if tool_exec_result.status == ToolResultStatus.SUCCESS:
                    if isinstance(tool_exec_result.result, dict):
                        gemini_tool_result_payload.update(tool_exec_result.result)
                    else:
                        logger.warning("Tool result is not a dictionary. Skipping result update.")

                elif tool_exec_result.status == ToolResultStatus.ERROR:
                    gemini_tool_result_payload["error_message"] = tool_exec_result.error_details
                    if isinstance(tool_exec_result.result, dict):
                        gemini_tool_result_payload["details"] = tool_exec_result.result

                elif tool_exec_result.status == ToolResultStatus.CLARIFICATION_NEEDED:
                    gemini_tool_result_payload["clarification_needed"] = tool_exec_result.clarification_prompt
                    if isinstance(tool_exec_result.result, dict):
                        gemini_tool_result_payload["details"] = tool_exec_result.result

                else:
                    logger.error(f"Unexpected ToolResultStatus: {tool_exec_result.status}")
                    gemini_tool_result_payload["error_message"] = "Unexpected tool execution status."

                function_response_turn = ConversationTurn.function_turn(
                    ToolResult(
                        name=tool_exec_result.name,
                        response=gemini_tool_result_payload # Send structured result back
                    )
                )
                history.append(function_response_turn)
                await session_manager.append_turn(session_id, function_response_turn) # Persist tool result turn

                # 8.6.3 & 8.6.4 - Loop back to call Gemini again with the tool result included in history
                # The loop condition (current_turn < turn_limit) handles this.
                continue # Go to the next iteration of the while loop

            # Handle ERROR response from Gemini Client
            elif gemini_response.response_type == ResponseType.ERROR:
                logger.error(f"[Session: {session_id}] Received ERROR response from Gemini Client: {gemini_response.error_message}")
                # Don't save this error turn to history? Or save as a special type? For now, just return error to user.
                return ChatResponse(
                    session_id=session_id,
                    status=ResponseStatus.ERROR,
                    response_text=f"Sorry, I encountered an error communicating with the AI model: {gemini_response.error_message}"
                )
            else:
                 # Should not happen if GeminiResponse model is correct
                 logger.error(f"[Session: {session_id}] Received unexpected response type from Gemini Client: {gemini_response.response_type}")
                 raise ValueError("Unexpected Gemini response type")

        # If loop finishes without returning (hit turn limit)
        logger.warning(f"[Session: {session_id}] Reached maximum Gemini turn limit ({turn_limit}).")
        # Return last known state or generic error/clarification
        # Check the last turn in history
        last_turn = history[-1] if history else None
        if last_turn and last_turn.role == ConversationRole.FUNCTION:
             # Last thing was a tool result, maybe model couldn't respond?
             return ChatResponse(
                 session_id=session_id,
                 status=ResponseStatus.ERROR,
                 response_text="Sorry, I couldn't complete the request after processing the information. Please try rephrasing."
             )
        # Fallback generic message
        return ChatResponse(
            session_id=session_id,
            status=ResponseStatus.ERROR,
            response_text="Sorry, the request took too many steps to process. Please try simplifying your request."
        )

    except Exception as e:
        logger.exception(f"[Session: {session_id}] Unhandled exception during orchestration: {e}")
        # Return a generic internal server error response
        # Avoid exposing internal error details directly
        return ChatResponse(
            session_id=session_id,
            status=ResponseStatus.ERROR,
            response_text="Sorry, an unexpected internal error occurred. Please try again later."
        )

