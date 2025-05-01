# app/orchestration_service.py

import logging
import uuid
from typing import List, Dict, Any, Optional

# --- Interface Imports ---
# Assuming interfaces and models from previous tasks are defined and importable
try:
    # From Task ORCH-3 / main.py
    from endpoints import ChatRequest, ChatResponse, ResponseStatus, ErrorDetail # Or wherever these are defined
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
    # From calendar_api.py (Task 2)
    from calendar_api import AbstractCalendarClient

    # --- Placeholder Interfaces/Implementations ---
    # Define dummy classes if real ones aren't available yet
    class AbstractGeminiClient:
        async def send_to_gemini(self, request: GeminiRequest) -> GeminiResponse:
            # Dummy implementation
            logger.info("Dummy Gemini Client: Processing request...")
            # Simulate function call on first turn if prompt mentions 'schedule'
            last_user_prompt = ""
            if request.history and request.history[-1].role == ConversationRole.USER:
                 # Assuming text is the first part
                 if isinstance(request.history[-1].parts[0], str):
                    last_user_prompt = request.history[-1].parts[0]


            if "schedule" in last_user_prompt.lower() and len(request.history) <= 1: # Only call function on first relevant prompt
                 logger.info("Dummy Gemini Client: Simulating function call response.")
                 return GeminiResponse(
                     response_type=ResponseType.FUNCTION_CALL,
                     function_call=FunctionCall(name="schedule_activity", args={"title": "Extracted Task", "duration_minutes": 60, "category_str": "WORK"})
                 )
            elif request.history and request.history[-1].role == ConversationRole.FUNCTION:
                 logger.info("Dummy Gemini Client: Simulating text response after function call.")
                 tool_resp = request.history[-1].parts[0] # Assuming ToolResult is the first part
                 return GeminiResponse(
                     response_type=ResponseType.TEXT,
                     text=f"OK, I processed the tool result: {tool_resp.response.get('message', 'Done.')}"
                 )
            else:
                 logger.info("Dummy Gemini Client: Simulating simple text response.")
                 return GeminiResponse(
                     response_type=ResponseType.TEXT,
                     text=f"Understood: '{last_user_prompt}'. Processing complete."
                 )

    class AbstractToolExecutor:
         async def execute_tool(self, call: FunctionCall, context: ExecutionContext) -> ExecutorToolResult:
             # Dummy implementation
             logger.info(f"Dummy Tool Executor: Executing '{call.name}'...")
             if call.name == "schedule_activity":
                 # Simulate success
                 return ExecutorToolResult(
                     name=call.name,
                     status=ToolResultStatus.SUCCESS,
                     result={"message": "Dummy: Activity scheduled.", "event_id": f"evt_{uuid.uuid4()}"}
                 )
             else:
                 return ExecutorToolResult(
                     name=call.name,
                     status=ToolResultStatus.ERROR,
                     error_details=f"Dummy: Unknown tool '{call.name}'"
                 )

    # Dummy function to get preferences (replace with real implementation)
    async def get_user_preferences(user_id: str) -> UserPreferences:
        logger.warning(f"Using DUMMY UserPreferences for user {user_id}")
        # Need a minimal UserPreferences object that passes validation if used
        class DummyPrefs(UserPreferences):
            def __init__(self, user_id: str):
                self.user_id = user_id
                self.time_zone = "UTC"  # Must be valid
                self.working_hours = {}  # Must be dict
                self.days_off = []

        return DummyPrefs(user_id)

    # Dummy Tool Registry (replace with real one from tool_wrappers.py)
    DUMMY_TOOL_DEFINITIONS: List[ToolDefinition] = [
        {
            "name": "schedule_activity",
            "description": "Schedules a task or event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Task title"},
                    "duration_minutes": {"type": "integer", "description": "Duration in minutes"},
                    "category_str": {"type": "string", "description": "Category (WORK, PERSONAL)"},
                    # Add other params as needed by the wrapper/schema
                },
                "required": ["title"]
            }
        }
    ]


except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.error(f"Failed to import dependencies for orchestration service: {e}. Service may not function.")


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
        if not history and request.session_id: # Check if session ID was provided but not found
             logger.warning(f"[Session: {session_id}] Provided session ID not found, starting new history.")
             # Optionally create session explicitly if needed by append_turn implementation
             # await session_manager.create_session(user_id, session_id) # If create takes session_id
        elif not history:
             logger.info(f"[Session: {session_id}] No history found, starting new session.")
             # Create session if it doesn't exist (create_session should handle this)
             # If create_session was already called implicitly by get_history or needs explicit call:
             # await session_manager.create_session(user_id, session_id) # If create takes session_id

        preferences = await get_user_preferences(user_id) # Task ORCH-9 (using dummy here)

        # Append current user prompt to history
        user_turn = ConversationTurn.user_turn(prompt_text)
        history.append(user_turn)
        await session_manager.append_turn(session_id, user_turn) # Persist user turn

        # 8.3 Get available tools (replace DUMMY with actual registry access)
        available_tools = DUMMY_TOOL_DEFINITIONS # Task ORCH-7

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
                tool_exec_result: ExecutorToolResult = await tool_executor.execute_tool(
                    call=gemini_response.function_call,
                    context=exec_context
                )
                logger.info(f"[Session: {session_id}] Tool execution result: {tool_exec_result.status}")

                # 8.6.2 Format tool result for Gemini history
                # Convert ExecutorToolResult into the ToolResult structure expected by Gemini API history
                # The 'response' dict should contain the data Gemini needs to formulate its final text response.
                gemini_tool_result_payload = {
                     "status": tool_exec_result.status.value,
                     # Include relevant data based on status
                 }
                if tool_exec_result.status == ToolResultStatus.SUCCESS and tool_exec_result.result:
                    gemini_tool_result_payload.update(tool_exec_result.result)
                elif tool_exec_result.status == ToolResultStatus.ERROR:
                    gemini_tool_result_payload["error_message"] = tool_exec_result.error_details
                    if tool_exec_result.result: # Include extra error context if available
                         gemini_tool_result_payload["details"] = tool_exec_result.result
                elif tool_exec_result.status == ToolResultStatus.CLARIFICATION_NEEDED:
                     gemini_tool_result_payload["clarification_needed"] = tool_exec_result.clarification_prompt
                     if tool_exec_result.result: # Include extra context if available
                         gemini_tool_result_payload["details"] = tool_exec_result.result


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

