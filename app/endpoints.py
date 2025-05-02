# main.py (Orchestration Service API)

import uuid
import logging
from enum import Enum
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, status as http_status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field


from orchestration_service import handle_chat_request
# --- Import Abstract Interfaces for Dependency Injection ---
from session_manager import AbstractSessionManager, MongoSessionManager
from orchestration_service import AbstractGeminiClient
from orchestration_service import AbstractToolExecutor
from calendar_api import AbstractCalendarClient, GoogleCalendarAPIClient
from models import ChatRequest, ChatResponse, ErrorDetail, ResponseStatus
# --- Configuration ---
# In a real app, use environment variables or a config file
API_VERSION = "v1"
API_PREFIX = f"/{API_VERSION}"

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_session_manager() -> AbstractSessionManager:
    # Replace with logic to get/create a session manager instance
    # Might involve getting DB connection from another dependency
    logger.warning("Using dummy MongoSessionManager instance")
    return MongoSessionManager()  # Requires DB connection setup elsewhere


def get_gemini_client() -> AbstractGeminiClient:
    # Replace with logic to get/create a Gemini client instance
    logger.warning("Using dummy AbstractGeminiClient instance")
    return AbstractGeminiClient()


def get_tool_executor() -> AbstractToolExecutor:
    # Replace with logic to get/create a Tool Executor instance
    logger.warning("Using dummy AbstractToolExecutor instance")
    # This might involve loading tool wrappers into a registry
    return AbstractToolExecutor()


def get_calendar_client() -> AbstractCalendarClient:
    # Replace with logic to get/create a Calendar Client instance
    # This might involve handling authentication per user if not using service account
    logger.warning("Using dummy GoogleCalendarAPIClient instance")
    # Needs credential configuration
    try:
        # Attempt to create, might need error handling if creds missing
        return GoogleCalendarAPIClient()
    except Exception as e:
        logger.error(f"Failed to instantiate GoogleCalendarAPIClient: {e}")
        # Raise an exception that FastAPI can handle, e.g., 503 Service Unavailable
        raise HTTPException(status_code=503, detail="Calendar service client unavailable.")

# --- Pydantic Schemas (Task 3.2, 3.3, 3.4) ---


# --- Authentication Dependency (Task 3.4 / Guideline) ---
# Placeholder for JWT verification. In a real app, this would validate the token
# and potentially extract user information.
# Requires: pip install python-jose[cryptography] python-multipart passlib[bcrypt]
# from jose import JWTError, jwt
# from passlib.context import CryptContext
# from fastapi import Security # Use Security for more fine-grained control

# Simple Bearer token check for now
bearer_scheme = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    """
    Placeholder function to 'verify' a bearer token.
    In a real application, this would decode and validate the JWT.
    It should return the user identifier associated with the token.
    """
    token = credentials.credentials
    logger.info(f"Received token (placeholder verification): {token[:10]}...") # Log prefix only
    # --- Placeholder Logic ---
    # Here you would:
    # 1. Define SECRET_KEY, ALGORITHM.
    # 2. try: payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    # 3. except JWTError: raise HTTPException(status_code=401, detail="Invalid token")
    # 4. Extract user_id from payload.
    # 5. Check if user exists, token expiry etc.
    # 6. return user_id
    # --- End Placeholder ---

    # For now, just check if token exists and return a dummy user_id
    # WARNING: This is NOT secure and only for demonstration.
    if not token:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Let's pretend the token itself contains the user_id for this placeholder
    # In reality, you'd extract it *from* the decoded token payload.
    # We'll compare it to the user_id in the request body later if needed.
    dummy_user_id_from_token = "user_from_" + token[:5] # Dummy extraction
    logger.info(f"Placeholder verification successful for token, dummy user: {dummy_user_id_from_token}")
    return dummy_user_id_from_token # Return a dummy ID based on token


# --- FastAPI Application ---
app = FastAPI(
    title="Orion Orchestration Service",
    description="API service to handle user chat prompts and orchestrate LLM calls and tool execution.",
    version="0.1.0",
)

# --- API Endpoint (Task 3.1) ---
# --- API Endpoint (Improved with Dependency Injection) ---
@app.post(
    f"/v1/chat/prompt", # Define prefix directly or use API_PREFIX constant
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
    calendar_client: AbstractCalendarClient = Depends(get_calendar_client)
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
@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Orion Orchestration Service is running."}

# Define a Pydantic model for user creation
class CreateUserRequest(BaseModel):
    user_id: str
    email: str
    password: str  # In a real app, ensure this is hashed before storing

@app.post(
    "/v1/users/create",
    summary="Create a new user",
    description="Allows the creation of a new user without authentication.",
    tags=["Users"]
)
async def create_user(request: CreateUserRequest):
    """
    Endpoint to create a new user without requiring authentication.
    """
    # Example logic for user creation
    try:
        # Replace with actual database logic
        if request.user_id == "existing_user":
            raise HTTPException(
                status_code=400,
                detail="User ID already exists."
            )
        # Simulate user creation
        new_user = {
            "user_id": request.user_id,
            "email": request.email,
            "password": "hashed_" + request.password  # Simulate password hashing
        }
        return {"message": "User created successfully", "user": new_user}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while creating the user: {str(e)}"
        )

# --- Example of how to run (if this is main.py) ---
# Use uvicorn: pip install uvicorn
# Command: uvicorn main:app --reload

