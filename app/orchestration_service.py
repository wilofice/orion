import logging
import uuid
from datetime import time, timedelta, date, datetime
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types
import json

import time as time_module
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
# Import the tool execution result persistence function
from db import save_tool_execution_result
from system import build_system_instruction
from db import get_user_preferences as db_get_user_preferences
from models import InputMode, VoiceButtonPosition, ActivityCategory
import asyncio
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
    async def send_to_gemini(self, request: GeminiRequest, system_instruction: str) -> GeminiResponse:
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
        
        # Add system instruction for French responses
        config = types.GenerateContentConfig(
            tools=[tools],
            system_instruction=system_instruction
        )
        
        payload = {
            "model": "gemini-2.5-pro-preview-05-06",
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


async def get_user_preferences(user_id: str) -> UserPreferences:
    """Retrieve user preferences from DynamoDB and convert them."""
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
            energy[(datetime.strptime(start_s, "%H:%M").time(),
                    datetime.strptime(end_s, "%H:%M").time())] = EnergyLevel(level)

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
    except Exception:
        logger.exception(
            "Failed to parse stored user preferences, falling back to defaults"
        )
        return UserPreferences(user_id=user_id)
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
# Removed MAX_GEMINI_TURNS - now we continue until final response with safety limit of 50 iterations

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
    max_iterations = 12  # Safety limit to prevent infinite loops
    current_iteration = 0

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
        system_prompt = build_system_instruction(preferences.time_zone)

        # Append current user prompt to history
        user_turn = ConversationTurn.user_turn(prompt_text, audio_url=request.audio_url)
        history.append(user_turn)
        await session_manager.append_turn(session_id, user_turn) # Persist user turn

        # 8.3 Get available tools (replace DUMMY with actual registry access)
        available_tools = TOOL_DEFINITIONS # Task ORCH-7
        definitive_response = None
        while definitive_response == None:  # Continue until we get a final response
            current_iteration += 1
            
            # Safety check to prevent infinite loops
            if current_iteration > max_iterations:
                logger.error(f"[Session: {session_id}] Reached maximum iteration limit ({max_iterations}). Breaking loop.")
                break
                
            logger.info(f"[Session: {session_id}] Gemini Iteration {current_iteration}")

            # 8.4 Build request and send to Gemini
            gemini_request = GeminiRequest(history=history, tools=available_tools)
            gemini_response = await gemini_client.send_to_gemini(
                gemini_request, system_prompt
            )

            # 8.5 Handle TEXT response
            if gemini_response.response_type == ResponseType.TEXT:
                logger.info(f"[Session: {session_id}] Received TEXT response from Gemini.")
                model_turn = ConversationTurn.model_turn_text(gemini_response.text)
                history.append(model_turn)
                await session_manager.append_turn(session_id, model_turn) # Persist model turn
                definitive_response = ChatResponse(
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
                
                # Generate execution ID and measure execution time
                execution_id = str(uuid.uuid4())
                start_time = time_module.time()
                
                tool_exec_result: ExecutorToolResult = tool_executor.execute_tool(
                    call=gemini_response.function_call,
                    context=exec_context
                )
                
                # Calculate execution duration
                end_time = time_module.time()
                duration_ms = int((end_time - start_time) * 1000)
                
                logger.info(f"[Session: {session_id}] Tool execution result: {tool_exec_result.status}")
                
                # Save tool execution result to DynamoDB
                save_result = save_tool_execution_result(
                    session_id=session_id,
                    execution_id=execution_id,
                    user_id=user_id,
                    tool_name=gemini_response.function_call.name,
                    function_call={
                        "name": gemini_response.function_call.name,
                        "args": gemini_response.function_call.args
                    },
                    execution_result=tool_exec_result.result if tool_exec_result.result else {},
                    status=tool_exec_result.status.value,
                    error_details=tool_exec_result.error_details,
                    duration_ms=duration_ms
                )
                
                if save_result != "success":
                    logger.warning(f"Failed to save tool execution result: {save_result}")

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
                # The loop will continue until Gemini provides a final text response
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

        # If loop finishes without returning (hit iteration limit)
        logger.warning(f"[Session: {session_id}] Reached maximum iteration limit ({max_iterations}).")
        # Return last known state or generic error/clarification
        # Check the last turn in history

        if definitive_response:
            return definitive_response
        last_turn = history[-1] if history else None
        if last_turn and last_turn.role == ConversationRole.FUNCTION_CALL:
             # Last thing was a tool result, maybe model couldn't respond?
             return ChatResponse(
                 session_id=session_id,
                 status=ResponseStatus.ERROR,
                 response_text="Sorry, I couldn't complete the request after processing the information. The system reached its safety limit. Please try rephrasing your request."
             )
        # Fallback generic message
        return ChatResponse(
            session_id=session_id,
            status=ResponseStatus.ERROR,
            response_text="Sorry, the request required too many processing steps and reached the safety limit. Please try simplifying your request."
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

