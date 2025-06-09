import logging
import threading
from google import genai
from google.genai import types
from settings_v1 import settings
from gemini_interface import (
    GeminiRequest,
    GeminiResponse,
    ResponseType,
    FunctionCall,
)

logger = logging.getLogger(__name__)


class GenAIClientSingleton:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize(*args, **kwargs)
        return cls._instance

    def _initialize(self, *args, **kwargs):
        self.client = self._create_genai_client(*args, **kwargs)

    def _create_genai_client(self, *args, **kwargs):
        return genai.Client(api_key=settings.GEMINI_API_KEY)

    @staticmethod
    def get_instance(*args, **kwargs):
        return GenAIClientSingleton(*args, **kwargs).client


class AbstractGeminiClient:
    async def send_to_gemini(
        self, request: GeminiRequest, system_instruction: str
    ) -> GeminiResponse:
        logger.info("Sending request to Gemini API")

        tools = types.Tool(function_declarations=request.tools)
        config = types.GenerateContentConfig(
            tools=[tools], system_instruction=system_instruction
        )

        payload = {
            "model": "gemini-2.5-pro-preview-05-06",
            "contents": [turn.parts[0] for turn in request.history],
            "config": config,
        }

        try:
            client = GenAIClientSingleton.get_instance()
            response = client.models.generate_content(**payload)

            part = response.candidates[0].content.parts[0]
            if part.function_call:
                fc = part.function_call
                logger.info("Received FUNCTION_CALL: %s", fc.name)
                return GeminiResponse(
                    response_type=ResponseType.FUNCTION_CALL,
                    function_call=FunctionCall(name=fc.name, args=fc.args),
                )
            if part.text:
                logger.info("Received TEXT response")
                return GeminiResponse(response_type=ResponseType.TEXT, text=part.text)

            logger.error("Unexpected response format from Gemini API")
            return GeminiResponse(
                response_type=ResponseType.ERROR,
                error_message="Unexpected response format from Gemini API.",
            )
        except Exception as e:  # pragma: no cover - network failure
            logger.exception("Error while communicating with Gemini API")
            return GeminiResponse(
                response_type=ResponseType.ERROR, error_message=str(e)
            )
