import httpx # Added for making HTTP requests
from fastapi import Depends, HTTPException, status, Body
from pydantic import BaseModel, AnyUrl  # HttpUrl removed, AnyUrl could be an alternative
from typing import Annotated, Dict, Any, Optional
import uuid
import json
import base64

from dynamodb import save_user_tokens, get_decrypted_user_tokens, delete_user_tokens, \
    refresh_google_access_token, encrypt_token, decrypt_token
from settings_v1 import settings
from core.security import create_access_token, get_current_user
from pydantic import (BaseModel, Field, field_validator,
                      model_validator)
# Imports for encryption
# --- Configuration ---

# Imports for DynamoDB
import time # For timestamps


from fastapi import APIRouter, HTTPException, status

# Initialize an APIRouter instance for user-related routes
# The 'prefix' adds '/users' before all paths defined in this router.
# 'tags' helps organize documentation in Swagger UI.
router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# --- Encryption Utilities ---
# AES-256 GCM uses a 12-byte (96-bit) IV by convention.
AES_GCM_IV_LENGTH_BYTES = 12


# --- Placeholder User Authentication ---
# This is a very basic placeholder. In a real application,
# you would integrate a proper authentication system (e.g., OAuth2 with JWTs for your app).

# Dummy user model (replace with your actual user model from DynamoDB later)
class User(BaseModel):
    id: str
    username: str


# Current user dependency using JWT authentication
async def get_authenticated_user(user_info: Dict[str, Any] = Depends(get_current_user)) -> User:
    """
    Get the authenticated user from the JWT token.
    Converts the user_info dict from JWT into a User object.
    """
    return User(id=user_info["user_id"], username=user_info.get("email", "unknown"))



class GoogleAuthCodePayload(BaseModel):
    """
    Request body for sending Google authorization code to the backend.
    """
    authorization_code: str
    platform: str
    code_verifier: str
    # Using HttpUrl for basic validation that it's a URL.
    # Further validation (e.g., matching against pre-registered URIs) can be added.
    redirect_uri: str # Ensures it's a valid URL format

    # Example for stricter validation if needed:
    # @validator('authorization_code')
    # def code_must_not_be_empty(cls, v):
    #     if not v.strip():
    #         raise ValueError('authorization_code must not be empty')
    #     return v


class UserInfo(BaseModel):
    """
    User information extracted from Google ID token.
    """
    email: str
    google_user_id: str


class TokenInfo(BaseModel):
    """
    Information about which tokens were received from Google.
    """
    access_token_present: bool
    refresh_token_present: bool
    id_token_present: bool
    scopes: Optional[str] = None


class AuthResponse(BaseModel):
    """
    Response model for successful Google OAuth authentication.
    """
    message: str
    user_id: str
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # Token expiration time in seconds
    user_info: UserInfo
    tokens_received: TokenInfo


class DisconnectResponse(BaseModel):
    """
    Response model for disconnecting Google Calendar.
    """
    message: str


class CurrentUserResponse(BaseModel):
    """
    Response model for current user information.
    """
    user_id: str
    username: str
    authenticated: bool


class ErrorResponse(BaseModel):
    """
    Standard error response model.
    """
    detail: str


# --- API Routers ---
# We'll define routers for different parts of the API.
# For now, we'll create stubs for the Google OAuth related endpoints.


CurrentUser = Annotated[User, Depends(get_authenticated_user)]

@router.post(
    "/google/connect", 
    response_model=AuthResponse, 
    tags=["Authentication"],
    summary="Exchange Google authorization code for JWT",
    description="Exchanges a Google OAuth authorization code for access/refresh tokens and generates a JWT for API authentication.",
    responses={
        200: {
            "description": "Successfully authenticated and generated JWT",
            "model": AuthResponse
        },
        400: {
            "description": "Invalid request (bad platform or OAuth error)",
            "model": ErrorResponse
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse
        },
        503: {
            "description": "Google authentication service unavailable",
            "model": ErrorResponse
        }
    }
)
async def connect_google_calendar(
        payload: GoogleAuthCodePayload = Body(...)
) -> AuthResponse:
    """
    Receives the Google authorization code from the mobile app,
    exchanges it with Google for access and refresh tokens,
    and generates a JWT bearer token for subsequent API calls.
    
    The returned JWT token should be included in the Authorization header
    for all subsequent API requests as: `Authorization: Bearer <token>`
    """
    #print(f"Received Google auth code for user: {current_user.id}")
    print(f"  Redirect URI from payload: {payload.redirect_uri}")
    print(f"  Redirect URI from payload: {payload.authorization_code}")
    print(f"  Redirect URI from payload: {payload.code_verifier}")

    if payload.platform not in ["ios", "android"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid platform. Must be 'ios' or 'android'.")
    if payload.platform == "ios":
        client_id = settings.GOOGLE_CLIENT_ID_IOS
    elif payload.platform == "android":
        client_id = settings.GOOGLE_CLIENT_ID_ANDROID

    token_request_data_ = {
        "code": payload.authorization_code,
        "client_id": client_id,
        "redirect_uri": payload.redirect_uri,  # Use the URI received from the client
        "grant_type": "authorization_code", # This should be correct
        "code_verifier": payload.code_verifier,
    }

    async with httpx.AsyncClient() as client:
        try:
            print(f"Requesting tokens from Google: {settings.GOOGLE_TOKEN_URL}")
            response = await client.post("https://oauth2.googleapis.com/token", data=token_request_data_, headers={"Content-Type": "application/x-www-form-urlencoded"})
            response.raise_for_status()  # Raises an HTTPStatusError for 4xx/5xx responses

            google_tokens: Dict[str, Any] = response.json()
            print("Successfully fetched tokens from Google.")

            # IMPORTANT: Do NOT log full tokens in production.
            # This is for development/debugging purposes for this task.
            # In subsequent tasks, these will be encrypted and stored.
            print(f"  Access Token (type): {type(google_tokens.get('access_token'))}")
            print(f"  Refresh Token (type): {type(google_tokens.get('refresh_token'))}")  # May not always be present
            print(f"  ID Token (type): {type(google_tokens.get('id_token'))}")  # If openid scope was requested
            print(f"  Expires In (seconds): {google_tokens.get('expires_in')}")
            print(f"  Scopes: {google_tokens.get('scope')}")

            # STUB: Token Encryption & Storage (To be implemented in Tasks 2.2, 2.3, 2.4)
            # 1. Validate id_token (if present) to get google_user_id.
            # 2. Encrypt access_token and refresh_token.
            # 3. Store encrypted tokens, expiry, scopes, google_user_id in DynamoDB, linked to current_user.id.

            # Example usage of encryption (actual storage in Task 2.3/2.4)
            if "access_token" in google_tokens:
                access_token = google_tokens["access_token"]
                try:
                    iv_access, ct_access, tag_access = encrypt_token(access_token, settings.ENCRYPTION_KEY_BYTES)
                    print(
                        f"Access Token encrypted. IV length: {len(iv_access)}, CT length: {len(ct_access)}, Tag length: {len(tag_access)}")

                    # Example decryption (for testing the utils)
                    decrypted_access_token = decrypt_token(iv_access, ct_access, tag_access,
                                                           settings.ENCRYPTION_KEY_BYTES)
                    if decrypted_access_token == access_token:
                        print("Access Token decryption successful (test).")
                    else:
                        print("ERROR: Access Token decryption test FAILED.")
                except Exception as e:
                    print(f"ERROR during access token encryption/decryption test: {e}")

            if "refresh_token" in google_tokens:
                refresh_token = google_tokens["refresh_token"]
                try:
                    iv_refresh, ct_refresh, tag_refresh = encrypt_token(refresh_token, settings.ENCRYPTION_KEY_BYTES)
                    print(
                        f"Refresh Token encrypted. IV length: {len(iv_refresh)}, CT length: {len(ct_refresh)}, Tag length: {len(tag_refresh)}")
                    # Example decryption (for testing the utils)
                    decrypted_refresh_token = decrypt_token(iv_refresh, ct_refresh, tag_refresh,
                                                            settings.ENCRYPTION_KEY_BYTES)
                    if decrypted_refresh_token == refresh_token:
                        print("Refresh Token decryption successful (test).")
                    else:
                        print("ERROR: Refresh Token decryption test FAILED.")
                except Exception as e:
                    print(f"ERROR during refresh token encryption/decryption test: {e}")

              # Added for generating GUIDs
            new_user_id = str(uuid.uuid4())  # Generate a unique GUID for the user
            save_success = save_user_tokens(
                app_user_id=new_user_id,  # Generate a unique GUID for the user
                access_token=access_token,
                access_token_expires_in=google_tokens.get('expires_in'),
                scopes=google_tokens.get('scope'),
                refresh_token=refresh_token,
                id_token_str=google_tokens.get('id_token')
            )

            if not save_success == "success":
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail=save_success)

            # Test retrieval (optional, for debugging this task)
            retrieved_tokens = get_decrypted_user_tokens(new_user_id)
            if retrieved_tokens:
                print(f"TEST: Successfully retrieved and decrypted tokens for {new_user_id}")
                print(
                    f"TEST: Retrieved access token matches original: {retrieved_tokens.get('access_token') == access_token}")
            else:
                print(f"TEST: Failed to retrieve/decrypt tokens for {new_user_id}")

            # Parse the Google ID token to get user information
            google_user_info = {}
            if "id_token" in google_tokens:
                try:
                    # Decode the ID token (without verification for now - in production, verify with Google's public keys)
                    # The ID token is a JWT with 3 parts separated by dots
                    id_token_parts = google_tokens["id_token"].split(".")
                    if len(id_token_parts) == 3:
                        # Decode the payload (second part)
                        # Add padding if necessary
                        payload = id_token_parts[1]
                        payload += "=" * (4 - len(payload) % 4)
                        decoded_payload = base64.urlsafe_b64decode(payload)
                        google_user_info = json.loads(decoded_payload)
                        print(f"Google user info: email={google_user_info.get('email')}, sub={google_user_info.get('sub')}")
                except Exception as e:
                    print(f"Failed to decode ID token: {e}")
            
            # Generate JWT access token for our API
            jwt_payload = {
                "user_id": new_user_id,
                "email": google_user_info.get("email", ""),
                "google_user_id": google_user_info.get("sub", ""),
                "scopes": google_tokens.get("scope", "").split() if google_tokens.get("scope") else []
            }
            
            access_token = create_access_token(data=jwt_payload)
            
            # Create response using the AuthResponse model
            return AuthResponse(
                message="Successfully exchanged authorization code for Google tokens.",
                user_id=new_user_id,
                access_token=access_token,
                token_type="bearer",
                expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
                user_info=UserInfo(
                    email=google_user_info.get("email", ""),
                    google_user_id=google_user_info.get("sub", "")
                ),
                tokens_received=TokenInfo(
                    access_token_present="access_token" in google_tokens,
                    refresh_token_present="refresh_token" in google_tokens,
                    id_token_present="id_token" in google_tokens,
                    scopes=google_tokens.get("scope")
                )
            )

        except httpx.HTTPStatusError as e:
            # Error response from Google's token endpoint
            error_details = e.response.json() if e.response.content else {}
            print(f"HTTP error from Google: {e.response.status_code} - {error_details}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,  # Or map to a more specific error
                detail=f"Failed to exchange code with Google: {error_details.get('error_description', e.response.text)}"
            )
        except httpx.RequestError as e:
            # Network error or other issue with the request to Google
            print(f"Request error to Google: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not connect to Google authentication service: {str(e)}"
            )
        except Exception as e:
            # Catch any other unexpected errors during the process
            print(f"Unexpected error during token exchange: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred: {str(e)}"
            )


@router.post(f"/auth/google/disconnect", response_model=DisconnectResponse, tags=["Authentication"])
async def disconnect_google_calendar(current_user: CurrentUser) -> DisconnectResponse:
    # Example usage of delete_user_tokens
    success = delete_user_tokens(current_user.id)
    if success:
        return DisconnectResponse(message="Successfully disconnected Google Calendar and deleted tokens.")
    else:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete user tokens.")


@router.get(f"/calendar/meta/list-calendars", tags=["Calendar"])
async def list_google_calendars(current_user: CurrentUser):
    tokens = get_decrypted_user_tokens(current_user.id)
    if not tokens or 'access_token' not in tokens:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User tokens not found or invalid.")
    # Example of how refresh logic might be triggered (actual trigger in Task 3.2)
    if tokens.get('access_token_expires_at', 0) < time.time() + 60:  # If expires in next 60s
        print(f"Access token for {current_user.id} is expired or nearing expiry. Attempting refresh...")
        new_access_token = await refresh_google_access_token(current_user.id)
        if not new_access_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Failed to refresh access token. Please reconnect Google Calendar.")
        tokens['access_token'] = new_access_token  # Use the new token for this request
        # The expiry would also be updated in DB, but for this immediate request, we use the new token.

    return {"message": "Tokens available.", "user_id": current_user.id,
            "access_token_snippet": tokens['access_token'][:10] + "..."}


@router.post(f"/auth/google/refresh-test", tags=["Authentication"])
async def test_refresh_token(current_user: CurrentUser):
    new_token = await refresh_google_access_token(current_user.id)
    if new_token:
        return {"message": "Token refresh attempted successfully.", "new_access_token_snippet": new_token[:10] + "..."}
    else:
        return {"message": "Token refresh failed or no refresh token available."}


@router.get("/me", response_model=CurrentUserResponse, tags=["Authentication"])
async def get_current_user_info(current_user: CurrentUser) -> CurrentUserResponse:
    """
    Get the currently authenticated user's information from the JWT token.
    """
    return CurrentUserResponse(
        user_id=current_user.id,
        username=current_user.username,
        authenticated=True
    )
