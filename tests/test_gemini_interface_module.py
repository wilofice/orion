import json
from app.gemini_interface import (
    FunctionCall,
    ToolResult,
    ConversationTurn,
    ConversationRole,
    GeminiRequest,
    GeminiResponse,
    ResponseType,
)


def test_conversation_turn_helpers():
    fc = FunctionCall(name="do", args={"a": 1})
    tr = ToolResult(name="do", response={"status": "ok"})

    user_turn = ConversationTurn.user_turn("hi")
    fc_turn = ConversationTurn.model_turn_function_call(fc)
    func_turn = ConversationTurn.function_turn(tr)
    text_turn = ConversationTurn.model_turn_text("bye")

    assert user_turn.role is ConversationRole.USER
    assert user_turn.parts == ["USER: hi"]
    assert fc_turn.role is ConversationRole.MODEL
    assert "AI FUNCTION CALL" in fc_turn.parts[0]
    assert func_turn.role is ConversationRole.FUNCTION
    assert "FUNCTION RESULT" in func_turn.parts[0]
    assert text_turn.parts == ["AI: bye"]


def test_request_and_response_models():
    turn = ConversationTurn.user_turn("hello")
    req = GeminiRequest(history=[turn], tools=[{"name": "t"}])
    resp = GeminiResponse(response_type=ResponseType.TEXT, text="out")

    assert req.history[0].role is ConversationRole.USER
    assert json.loads(resp.model_dump_json())["text"] == "out"
