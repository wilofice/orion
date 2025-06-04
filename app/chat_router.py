import logging

from fastapi import FastAPI, Depends, HTTPException, status as http_status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from orchestration_service import handle_chat_request
# --- Import Abstract Interfaces for Dependency Injection ---
from session_manager import AbstractSessionManager, DynamoSessionManager
from orchestration_service import AbstractGeminiClient
from orchestration_service import AbstractToolExecutor
from calendar_client import AbstractCalendarClient
from app.services import get_calendar_client_for_user as service_get_calendar_client_for_user
from models import ChatRequest, ChatResponse, ErrorDetail
from core.security import verify_token as jwt_verify_token

from mangum import Mangum
# --- Configuration ---
# In a real app, use environment variables or a config file


from fastapi import APIRouter, HTTPException, status

# Initialize an APIRouter instance for user-related routes
# The 'prefix' adds '/users' before all paths defined in this router.
# 'tags' helps organize documentation in Swagger UI.
router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_session_manager() -> AbstractSessionManager:
    """Return the session manager implementation used by the API."""
    # In production this could fetch an instance from a dependency
    # injection container or create it lazily.  For now we always use
    # the DynamoDB backed implementation.
    logger.warning("Using DynamoSessionManager instance")
    return DynamoSessionManager()


def get_gemini_client() -> AbstractGeminiClient:
    """Factory for the Gemini LLM client used during orchestration."""
    # A real implementation would construct a client connected to the
    # Gemini API.  The tests use this placeholder instance.
    logger.warning("Using dummy AbstractGeminiClient instance")
    return AbstractGeminiClient()


def get_tool_executor() -> AbstractToolExecutor:
    """Return the component responsible for executing tool calls."""
    # This could wire up a registry of tool wrappers in a more complex
    # application.  At the moment it simply returns a stub executor used
    # in unit tests.
    logger.warning("Using dummy AbstractToolExecutor instance")
    return AbstractToolExecutor()


def get_calendar_client(user_id: str) -> AbstractCalendarClient:
    """Return a calendar client for the given user."""
    try:
        return service_get_calendar_client_for_user(user_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to instantiate calendar client: {e}")
        raise HTTPException(status_code=503, detail="Calendar service client unavailable.")

# --- Pydantic Schemas (Task 3.2, 3.3, 3.4) ---


# --- Authentication Dependency (Task 3.4 / Guideline) ---
# Placeholder for JWT verification. In a real app, this would validate the token
# and potentially extract user information.
# Requires: pip install python-jose[cryptography] python-multipart passlib[bcrypt]
# from jose import JWTError, jwt
# from passlib.context import CryptContext
# from fastapi import Security # Use Security for more fine-grained control

# The verify_token function is now imported from core.security module
# It properly decodes and validates JWT tokens
bearer_scheme = HTTPBearer()

# Use the imported JWT verify_token function
verify_token = jwt_verify_token


# --- FastAPI Application ---


# --- API Endpoint (Task 3.1) ---
# --- API Endpoint (Improved with Dependency Injection) ---
@router.post(
    f"/prompt", # Define prefix directly or use API_PREFIX constant
    response_model=ChatResponse,
    summary="Process a user chat prompt",
    description="Sends user input to the Orion orchestration service for processing via LLM and potential tool execution.",
    tags=["Chat"],
    responses={
        400: {"model": ErrorDetail, "description": "Bad Request"},
        401: {"model": ErrorDetail, "description": "Unauthorized"},
        429: {"model": ErrorDetail, "description": "Too Many Requests"},
        500: {"model": ErrorDetail, "description": "Internal Server Error"},
        503: {"model": ErrorDetail, "description": "Service Unavailable"},
    }
)
async def process_chat_prompt(
    request: ChatRequest,
    # --- Authentication ---
    # Run authentication dependency. It should return the user_id from the token.
    user_id_from_token: str = Depends(verify_token),
    # --- Inject Dependencies using Depends ---
    session_manager: AbstractSessionManager = Depends(get_session_manager),
    gemini_client: AbstractGeminiClient = Depends(get_gemini_client),
    tool_executor: AbstractToolExecutor = Depends(get_tool_executor),
) -> ChatResponse:
    """
    Handles incoming user chat prompts by calling the core orchestration logic
    with injected dependencies.
    """
    logger.info(f"API Endpoint: Received chat prompt for user: {request.user_id}, session: {request.session_id}")

    # --- Authorization Check (Optional but Recommended) ---
    # Ensure the user_id from the token matches the one in the request body

    if user_id_from_token != request.user_id:
        logger.warning(f"Token user ID '{user_id_from_token}' does not match request user ID '{request.user_id}'.")
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="User ID mismatch - cannot process request for another user."
        )
    logger.info(f"User '{user_id_from_token}' authorized.")

    calendar_client = get_calendar_client(request.user_id)

    # --- Call the core orchestration logic ---
    try:
        # Pass the request and the resolved dependencies to the handler function
        response = await handle_chat_request(
            request=request,
            session_manager=session_manager,
            gemini_client=gemini_client,
            tool_executor=tool_executor,
            calendar_client=calendar_client
            # user_preferences are loaded inside handle_chat_request based on user_id
        )
        return response
    except ImportError as e:
         # Catch import error from the handler if dummies were used or dependencies failed
         logger.exception("ImportError during request handling, likely due to missing dependencies.")
         raise HTTPException(
             status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, # 503 might be more appropriate
             detail=f"Core service components are not available."
         )
    except HTTPException as e:
         # Re-raise known HTTP exceptions (like from verify_token or dependency providers)
         raise e
    except Exception as e:
        # Catch unexpected errors from the handler (though it should handle its own)
        logger.exception(f"Unexpected error processing request for user {request.user_id}, session {request.session_id}: {e}")
        raise HTTPException(
             status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
             detail="An unexpected error occurred while processing your request.")


# --- Root Endpoint (Optional - for health check/info) ---
@router.get("/", include_in_schema=False)
async def root():
    return {"message": "Orion Orchestration Service is running."}

