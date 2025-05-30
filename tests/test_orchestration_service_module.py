import pytest
from app import orchestration_service as orch
from app.models import ChatRequest, ResponseStatus
from app.gemini_interface import GeminiResponse, ResponseType, FunctionCall


class DummySessionManager(orch.AbstractSessionManager):
    def __init__(self):
        self.history = []

    async def get_history(self, session_id: str):
        return list(self.history)

    async def append_turn(self, session_id: str, turn):
        self.history.append(turn)

    async def create_session(self, user_id: str, session_id: str):
        self.history = []
        return session_id


class DummyGeminiClient(orch.AbstractGeminiClient):
    def __init__(self, responses):
        self.responses = responses

    async def send_to_gemini(self, request):
        return self.responses.pop(0)


class DummyToolExecutor(orch.AbstractToolExecutor):
    def __init__(self, executed):
        self.executed = executed

    def execute_tool(self, call, context):
        self.executed.append(call.name)
        return orch.ExecutorToolResult(name=call.name, status=orch.ToolResultStatus.SUCCESS, result={})


class DummyCalendarClient(orch.AbstractCalendarClient):
    def authenticate(self):
        pass

    def get_busy_slots(self, *a, **k):
        return []

    def calculate_free_slots(self, *a, **k):
        return []

    def get_available_time_slots(self, *a, **k):
        return []

    def add_event(self, *a, **k):
        return {}


import asyncio


def test_handle_chat_request_text(monkeypatch):
    session = DummySessionManager()
    gemini = DummyGeminiClient([GeminiResponse(response_type=ResponseType.TEXT, text="hi")])
    executed = []
    tool_exec = DummyToolExecutor(executed)
    cal = DummyCalendarClient()

    monkeypatch.setattr(orch, "TOOL_DEFINITIONS", [])
    async def dummy_prefs(uid):
        return orch.DummyPrefs(user_id=uid)
    monkeypatch.setattr(orch, "get_user_preferences", dummy_prefs)

    req = ChatRequest(user_id="u1", session_id="s1", prompt_text="hello")
    resp = asyncio.run(
        orch.handle_chat_request(req, session, gemini, tool_exec, cal)
    )
    assert resp.status == ResponseStatus.COMPLETED
    assert resp.response_text == "hi"
    assert executed == []


def test_handle_chat_request_function_call(monkeypatch):
    session = DummySessionManager()
    fc = FunctionCall(name="do", args={})
    responses = [
        GeminiResponse(response_type=ResponseType.FUNCTION_CALL, function_call=fc),
        GeminiResponse(response_type=ResponseType.TEXT, text="done"),
    ]
    gemini = DummyGeminiClient(responses)
    executed = []
    tool_exec = DummyToolExecutor(executed)
    cal = DummyCalendarClient()

    monkeypatch.setattr(orch, "TOOL_DEFINITIONS", [])
    async def dummy_prefs(uid):
        return orch.DummyPrefs(user_id=uid)
    monkeypatch.setattr(orch, "get_user_preferences", dummy_prefs)

    req = ChatRequest(user_id="u1", session_id="s1", prompt_text="hi")
    resp = asyncio.run(
        orch.handle_chat_request(req, session, gemini, tool_exec, cal)
    )
    assert executed == ["do"]
    assert resp.status == ResponseStatus.COMPLETED
    assert resp.response_text == "done"
