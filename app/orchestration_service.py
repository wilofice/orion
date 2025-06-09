import logging
import uuid
import time as time_module
from typing import List

from gemini_interface import (
    GeminiRequest,
    ConversationTurn,
    ResponseType,
    ToolResult,
    ConversationRole,
)
from tool_interface import ExecutionContext, ExecutorToolResult, ToolResultStatus
from session_manager import AbstractSessionManager
from calendar_client import AbstractCalendarClient
from models import ChatRequest, ChatResponse, ResponseStatus, UserPreferences
from system import build_system_instruction
from db import save_tool_execution_result

# Import implementations split into separate modules
from gemini_client_impl import AbstractGeminiClient
from tool_executor_impl import AbstractToolExecutor
from preferences_loader import get_user_preferences
from tool_definitions import TOOL_DEFINITIONS

logger = logging.getLogger(__name__)


def _log(session_id: str, message: str, level: int = logging.INFO) -> None:
    """Helper to format log messages consistently."""
    logger.log(level, f"[session={session_id}] {message}")


async def handle_chat_request(
    request: ChatRequest,
    session_manager: AbstractSessionManager,
    gemini_client: AbstractGeminiClient,
    tool_executor: AbstractToolExecutor,
    calendar_client: AbstractCalendarClient,
) -> ChatResponse:
    """Core orchestration logic to handle a user chat request."""
    session_id = request.session_id or str(uuid.uuid4())
    user_id = request.user_id
    prompt_text = request.prompt_text
    max_iterations = 12
    current_iteration = 0

    try:
        _log(session_id, f"Loading history for user {user_id}")
        history: List[ConversationTurn] = await session_manager.get_history(session_id)
        if not history:
            _log(
                session_id,
                "Provided session ID not found, starting new history",
                logging.WARNING,
            )
            await session_manager.create_session(user_id, session_id)
            history = await session_manager.get_history(session_id)

        preferences = await get_user_preferences(user_id)
        system_prompt = build_system_instruction(preferences.time_zone)

        user_turn = ConversationTurn.user_turn(prompt_text, audio_url=request.audio_url)
        history.append(user_turn)
        await session_manager.append_turn(session_id, user_turn)

        available_tools = TOOL_DEFINITIONS
        definitive_response = None
        while definitive_response is None:
            current_iteration += 1
            if current_iteration > max_iterations:
                _log(
                    session_id,
                    f"Reached maximum iteration limit {max_iterations}",
                    logging.ERROR,
                )
                break

            _log(session_id, f"Iteration {current_iteration}: calling Gemini")
            gemini_request = GeminiRequest(history=history, tools=available_tools)
            gemini_response = await gemini_client.send_to_gemini(
                gemini_request, system_prompt
            )

            if gemini_response.response_type == ResponseType.TEXT:
                _log(session_id, f"Iteration {current_iteration}: received text")
                model_turn = ConversationTurn.model_turn_text(gemini_response.text)
                history.append(model_turn)
                await session_manager.append_turn(session_id, model_turn)
                definitive_response = ChatResponse(
                    session_id=session_id,
                    status=ResponseStatus.COMPLETED,
                    response_text=gemini_response.text,
                )

            elif gemini_response.response_type == ResponseType.FUNCTION_CALL:
                fc = gemini_response.function_call
                _log(
                    session_id,
                    f"Iteration {current_iteration}: Gemini requested function '{fc.name}'",
                )
                model_fc_turn = ConversationTurn.model_turn_function_call(fc)
                history.append(model_fc_turn)
                await session_manager.append_turn(session_id, model_fc_turn)

                exec_context = ExecutionContext(
                    user_id=user_id,
                    preferences=preferences,
                    calendar_client=calendar_client,
                )

                execution_id = str(uuid.uuid4())
                start_time = time_module.time()
                tool_exec_result: ExecutorToolResult = tool_executor.execute_tool(
                    fc, exec_context
                )
                end_time = time_module.time()
                duration_ms = int((end_time - start_time) * 1000)
                _log(
                    session_id,
                    f"Tool '{fc.name}' executed in {duration_ms}ms with status {tool_exec_result.status}",
                )

                save_result = save_tool_execution_result(
                    session_id=session_id,
                    execution_id=execution_id,
                    user_id=user_id,
                    tool_name=fc.name,
                    function_call={"name": fc.name, "args": fc.args},
                    execution_result=(
                        tool_exec_result.result if tool_exec_result.result else {}
                    ),
                    status=tool_exec_result.status.value,
                    error_details=tool_exec_result.error_details,
                    duration_ms=duration_ms,
                )
                if save_result != "success":
                    _log(
                        session_id,
                        f"Failed to save tool execution result: {save_result}",
                        logging.WARNING,
                    )

                gemini_tool_result_payload = {"status": tool_exec_result.status.value}
                if tool_exec_result.status == ToolResultStatus.SUCCESS:
                    if isinstance(tool_exec_result.result, dict):
                        gemini_tool_result_payload.update(tool_exec_result.result)
                elif tool_exec_result.status == ToolResultStatus.ERROR:
                    gemini_tool_result_payload["error_message"] = (
                        tool_exec_result.error_details
                    )
                    if isinstance(tool_exec_result.result, dict):
                        gemini_tool_result_payload["details"] = tool_exec_result.result
                elif tool_exec_result.status == ToolResultStatus.CLARIFICATION_NEEDED:
                    gemini_tool_result_payload["clarification_needed"] = (
                        tool_exec_result.clarification_prompt
                    )
                    if isinstance(tool_exec_result.result, dict):
                        gemini_tool_result_payload["details"] = tool_exec_result.result
                else:
                    _log(
                        session_id,
                        f"Unexpected ToolResultStatus: {tool_exec_result.status}",
                        logging.ERROR,
                    )
                    gemini_tool_result_payload["error_message"] = (
                        "Unexpected tool execution status."
                    )

                function_response_turn = ConversationTurn.function_turn(
                    ToolResult(
                        name=tool_exec_result.name, response=gemini_tool_result_payload
                    )
                )
                history.append(function_response_turn)
                await session_manager.append_turn(session_id, function_response_turn)
                continue

            elif gemini_response.response_type == ResponseType.ERROR:
                _log(
                    session_id,
                    f"Gemini error: {gemini_response.error_message}",
                    logging.ERROR,
                )
                return ChatResponse(
                    session_id=session_id,
                    status=ResponseStatus.ERROR,
                    response_text=f"Sorry, I encountered an error communicating with the AI model: {gemini_response.error_message}",
                )
            else:
                _log(
                    session_id,
                    f"Unexpected Gemini response type: {gemini_response.response_type}",
                    logging.ERROR,
                )
                raise ValueError("Unexpected Gemini response type")

        _log(session_id, "Reached maximum iteration limit", logging.WARNING)
        if definitive_response:
            return definitive_response
        last_turn = history[-1] if history else None
        if last_turn and last_turn.role == ConversationRole.FUNCTION_CALL:
            return ChatResponse(
                session_id=session_id,
                status=ResponseStatus.ERROR,
                response_text="Sorry, I couldn't complete the request after processing the information. The system reached its safety limit. Please try rephrasing your request.",
            )
        return ChatResponse(
            session_id=session_id,
            status=ResponseStatus.ERROR,
            response_text="Sorry, the request required too many processing steps and reached the safety limit. Please try simplifying your request.",
        )
    except Exception as e:  # pragma: no cover - defensive
        logger.exception("Unhandled exception during orchestration", exc_info=e)
        return ChatResponse(
            session_id=session_id,
            status=ResponseStatus.ERROR,
            response_text="Sorry, an unexpected internal error occurred. Please try again later.",
        )
