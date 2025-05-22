from pathlib import Path

import httpx # Added for making HTTP requests
from fastapi import FastAPI, Depends, HTTPException, status, Body
from pydantic import BaseModel, AnyUrl  # HttpUrl removed, AnyUrl could be an alternative
from pydantic_settings import BaseSettings
from typing import Annotated, Optional, Dict, Any, Tuple

from settings_v1 import Settings
# Imports for encryption
import os # For generating random IV
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag # For handling decryption errors
# --- Configuration ---

# Imports for DynamoDB
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.types import Binary # To store bytes in DynamoDB
import time # For timestamps
import json # For decoding id_token (basic)
import base64
# .env.example
# Copy this file to .env and fill in your actual values.
# DO NOT commit your .env file to version control.


settings = Settings()

# --- Encryption Utilities ---
# AES-256 GCM uses a 12-byte (96-bit) IV by convention.
AES_GCM_IV_LENGTH_BYTES = 12


def encrypt_token(token_str: str, key: bytes) -> Tuple[bytes, bytes, bytes]:
    """
    Encrypts a token string using AES-256 GCM.c

    Args:
        token_str: The plaintext token string.
        key: The 32-byte encryption key.

    Returns:
        A tuple containing (iv, ciphertext, auth_tag).
        - iv: The 12-byte initialization vector.
        - ciphertext: The encrypted token.
        - auth_tag: The 16-byte authentication tag.
    """
    if not isinstance(token_str, str):
        raise TypeError("Token to encrypt must be a string.")
    if not token_str:  # Do not encrypt empty strings, handle upstream if needed
        raise ValueError("Cannot encrypt an empty token string.")

    aesgcm = AESGCM(key)
    iv = os.urandom(AES_GCM_IV_LENGTH_BYTES)  # Generate a random 12-byte IV

    token_bytes = token_str.encode('utf-8')
    ciphertext_with_tag = aesgcm.encrypt(iv, token_bytes, None)  # Associated data is None

    # GCM typically appends the tag to the ciphertext or it's handled separately.
    # The 'cryptography' library's AESGCM encrypt method returns ciphertext + tag.
    # Standard GCM tag size is 16 bytes (128 bits).
    tag_length = 16
    ciphertext = ciphertext_with_tag[:-tag_length]
    auth_tag = ciphertext_with_tag[-tag_length:]

    return iv, ciphertext, auth_tag


def decrypt_token(iv: bytes, ciphertext: bytes, auth_tag: bytes, key: bytes) -> str:
    """
    Decrypts a token using AES-256 GCM.

    Args:
        iv: The 12-byte initialization vector used for encryption.
        ciphertext: The encrypted token.
        auth_tag: The 16-byte authentication tag.
        key: The 32-byte encryption key.

    Returns:
        The decrypted plaintext token string.

    Raises:
        InvalidTag: If decryption fails due to incorrect key, tampered data, or wrong IV/tag.
    """
    if not all(isinstance(x, bytes) for x in [iv, ciphertext, auth_tag, key]):
        raise TypeError("All inputs (iv, ciphertext, auth_tag, key) for decryption must be bytes.")

    aesgcm = AESGCM(key)
    ciphertext_with_tag = ciphertext + auth_tag

    try:
        decrypted_bytes = aesgcm.decrypt(iv, ciphertext_with_tag, None)  # Associated data is None
        return decrypted_bytes.decode('utf-8')
    except InvalidTag:
        # This exception is raised if the authentication tag doesn't match,
        # indicating the data may have been tampered with or the key is wrong.
        print("ERROR: Decryption failed - InvalidTag. Check encryption key or data integrity.")
        raise  # Re-raise the exception to be handled by the caller


# --- DynamoDB Setup ---
def get_dynamodb_resource():
    if settings.AWS_DYNAMODB_ENDPOINT_URL:  # For local testing
        print(f"Connecting to DynamoDB Local at {settings.AWS_DYNAMODB_ENDPOINT_URL}")
        return boto3.resource('dynamodb',
                              region_name=settings.AWS_REGION,
                              endpoint_url=settings.AWS_DYNAMODB_ENDPOINT_URL)
    else:  # For AWS environment
        print(f"Connecting to DynamoDB in region {settings.AWS_REGION}")
        return boto3.resource('dynamodb', region_name=settings.AWS_REGION)


dynamodb_resource = get_dynamodb_resource()
user_tokens_table = dynamodb_resource.Table(settings.DYNAMODB_USER_TOKENS_TABLE_NAME)


# --- DynamoDB Token Persistence Logic ---
def save_user_tokens(
        app_user_id: str,
        access_token: str,
        access_token_expires_in: int,
        scopes: Optional[str] = None,
        refresh_token: Optional[str] = None,
        id_token_str: Optional[str] = None  # Raw ID token string
) -> bool:
    """
    Encrypts and saves Google OAuth tokens for a user in DynamoDB.
    Updates if tokens already exist for the user.
    """
    current_timestamp = int(time.time())
    access_token_expires_at = current_timestamp + access_token_expires_in

    iv_access, ct_access, tag_access = encrypt_token(access_token, settings.ENCRYPTION_KEY_BYTES)

    item = {
        'app_user_id': app_user_id,
        'encrypted_access_token': Binary(ct_access),  # Store bytes as Binary
        'iv_access_token': Binary(iv_access),
        'auth_tag_access_token': Binary(tag_access),
        'access_token_expires_at': access_token_expires_at,
        'updated_at': current_timestamp,
    }

    if scopes:
        # Storing scopes as a comma-separated string for simplicity.
        # Can also be stored as a String Set (SS) in DynamoDB if needed for querying.
        item['scopes'] = scopes

    google_user_id = None
    if id_token_str:
        # Basic decoding to get 'sub'. Proper validation is more complex.
        # WARNING: This is NOT proper ID token validation.
        # For production, use a library like google-auth to validate the ID token.
        try:
            # Split the JWT (header.payload.signature) and decode the payload part
            payload_part = id_token_str.split('.')[1]
            # Add padding if necessary for base64 decoding
            payload_part += '=' * (-len(payload_part) % 4)
            decoded_payload = json.loads(
                base64.urlsafe_b64decode().getUrlDecoder().decode(payload_part.encode('utf-8')).decode('utf-8'))
            google_user_id = decoded_payload.get('sub')
            if google_user_id:
                item['google_user_id'] = google_user_id
            print(f"Extracted google_user_id (sub): {google_user_id} from ID token (basic decode).")
        except Exception as e:
            print(f"Warning: Could not decode/extract 'sub' from ID token: {e}")

    if refresh_token:
        iv_refresh, ct_refresh, tag_refresh = encrypt_token(refresh_token, settings.ENCRYPTION_KEY_BYTES)
        item['encrypted_refresh_token'] = Binary(ct_refresh)
        item['iv_refresh_token'] = Binary(iv_refresh)
        item['auth_tag_refresh_token'] = Binary(tag_refresh)

    try:
        # Check if item exists to set created_at or just update updated_at
        response = user_tokens_table.get_item(Key={'app_user_id': app_user_id})
        if 'Item' not in response:
            item['created_at'] = current_timestamp

        user_tokens_table.put_item(Item=item)
        print(f"Successfully saved tokens for app_user_id: {app_user_id}")
        return True
    except ClientError as e:
        print(f"Error saving tokens to DynamoDB for {app_user_id}: {e.response['Error']['Message']}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred during token save: {e}")
        return False


def get_decrypted_user_tokens(app_user_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves and decrypts Google OAuth tokens for a user from DynamoDB.
    Returns None if no tokens found or decryption fails.
    """
    try:
        response = user_tokens_table.get_item(Key={'app_user_id': app_user_id})
        if 'Item' not in response:
            print(f"No tokens found in DynamoDB for app_user_id: {app_user_id}")
            return None

        item = response['Item']
        decrypted_tokens = {'app_user_id': item['app_user_id']}

        # Convert Binary back to bytes for decryption
        iv_access = bytes(item['iv_access_token'])
        ct_access = bytes(item['encrypted_access_token'])
        tag_access = bytes(item['auth_tag_access_token'])

        decrypted_tokens['access_token'] = decrypt_token(iv_access, ct_access, tag_access,
                                                         settings.ENCRYPTION_KEY_BYTES)
        decrypted_tokens['access_token_expires_at'] = int(item['access_token_expires_at'])

        if 'scopes' in item:
            decrypted_tokens['scopes'] = item['scopes']
        if 'google_user_id' in item:
            decrypted_tokens['google_user_id'] = item['google_user_id']

        if 'encrypted_refresh_token' in item:
            iv_refresh = bytes(item['iv_refresh_token'])
            ct_refresh = bytes(item['encrypted_refresh_token'])
            tag_refresh = bytes(item['auth_tag_refresh_token'])
            decrypted_tokens['refresh_token'] = decrypt_token(iv_refresh, ct_refresh, tag_refresh,
                                                              settings.ENCRYPTION_KEY_BYTES)

        print(f"Successfully retrieved and decrypted tokens for app_user_id: {app_user_id}")
        return decrypted_tokens

    except InvalidTag:  # Raised by decrypt_token if auth tag mismatch
        print(
            f"ERROR: Decryption failed (InvalidTag) for app_user_id: {app_user_id}. Tokens might be corrupted or key changed.")
        return None
    except ClientError as e:
        print(f"Error retrieving tokens from DynamoDB for {app_user_id}: {e.response['Error']['Message']}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during token retrieval/decryption: {e}")
        return None


def delete_user_tokens(app_user_id: str) -> bool:
    """Deletes Google OAuth tokens for a user from DynamoDB."""
    try:
        user_tokens_table.delete_item(Key={'app_user_id': app_user_id})
        print(f"Successfully deleted tokens for app_user_id: {app_user_id}")
        return True
    except ClientError as e:
        print(f"Error deleting tokens from DynamoDB for {app_user_id}: {e.response['Error']['Message']}")
        return False


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    root_path=f"{settings.API_V1_STR}"
)


# --- Placeholder User Authentication ---
# This is a very basic placeholder. In a real application,
# you would integrate a proper authentication system (e.g., OAuth2 with JWTs for your app).

# Dummy user model (replace with your actual user model from DynamoDB later)
class User:
    def __init__(self, id: str, username: str):
        self.id = id
        self.username = username


# Dummy current_user dependency (replace with actual auth logic)
async def get_current_user_placeholder() -> User:
    """
    Placeholder for current user dependency.
    In a real app, this would validate a token and fetch user details.
    For now, it returns a dummy user.
    """
    # In a real scenario, you'd decode a JWT, validate it,
    # and fetch the user from your database (DynamoDB).
    # If validation fails, raise HTTPException(status_code=401_UNAUTHORIZED, detail="Not authenticated")
    print("WARNING: Using placeholder authentication. Replace with actual implementation.")
    return User(id="dummy_user_id_123", username="testuser")



class GoogleAuthCodePayload(BaseModel):
    """
    Request body for sending Google authorization code to the backend.
    """
    email: str = None  # Optional email field, can be used for logging or debugging
    authorization_code: str
    platform: str
    client_id: str
    code_verifier: str
    # Using HttpUrl for basic validation that it's a URL.
    # Further validation (e.g., matching against pre-registered URIs) can be added.
    redirect_uri: AnyUrl # Ensures it's a valid URL format

    # Example for stricter validation if needed:
    # @validator('authorization_code')
    # def code_must_not_be_empty(cls, v):
    #     if not v.strip():
    #         raise ValueError('authorization_code must not be empty')
    #     return v


# --- API Routers ---
# We'll define routers for different parts of the API.
# For now, we'll create stubs for the Google OAuth related endpoints.

@app.get("/health", tags=["Health"])
async def health_check():
    """
    Simple health check endpoint.
    """
    return {"status": "healthy", "message": f"Welcome to {settings.PROJECT_NAME}"}

CurrentUser = Annotated[User, Depends(get_current_user_placeholder)]

@app.post("/auth/google/connect", tags=["Authentication"])
async def connect_google_calendar(
        payload: GoogleAuthCodePayload = Body(...),
        current_user: User = Depends(get_current_user_placeholder)
):
    """
    Receives the Google authorization code from the mobile app,
    and exchanges it with Google for access and refresh tokens.
    """
    print(f"Received Google auth code for user: {current_user.id}")
    print(f"  Redirect URI from payload: {payload.redirect_uri}")
    print(f"  Redirect URI from payload: {payload.authorization_code}")
    print(f"  Redirect URI from payload: {payload.code_verifier}")

    token_request_data_ = {
        "code": payload.authorization_code,
        "client_id": payload.client_id,
        "redirect_uri": payload.redirect_uri,  # Use the URI received from the client
        "grant_type": "authorization_code", # This should be correct
        "code_verifier": payload.code_verifier,
    }

    async with httpx.AsyncClient(verify=False) as client:
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


            save_success = save_user_tokens(
                app_user_id=current_user.id,
                access_token=access_token,
                access_token_expires_in=google_tokens.get('expires_in'),
                scopes=google_tokens.get('scope'),
                refresh_token=refresh_token,
                id_token_str=google_tokens.get('id_token')
            )

            if not save_success:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    detail="Failed to save user tokens to database.")

            # Test retrieval (optional, for debugging this task)
            retrieved_tokens = get_decrypted_user_tokens(current_user.id)
            if retrieved_tokens:
                print(f"TEST: Successfully retrieved and decrypted tokens for {current_user.id}")
                print(
                    f"TEST: Retrieved access token matches original: {retrieved_tokens.get('access_token') == access_token}")
            else:
                print(f"TEST: Failed to retrieve/decrypt tokens for {current_user.id}")

            return {
                "message": "Successfully exchanged authorization code for Google tokens.",
                "user_id": current_user.id,
                "tokens_received": {
                    "access_token_present": "access_token" in google_tokens,
                    "refresh_token_present": "refresh_token" in google_tokens,
                    "id_token_present": "id_token" in google_tokens,
                    "scopes": google_tokens.get("scope"),
                }
            }

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


@app.post(f"{settings.API_V1_STR}/auth/google/disconnect", tags=["Authentication"])
async def disconnect_google_calendar(current_user: CurrentUser):
    # Example usage of delete_user_tokens
    success = delete_user_tokens(current_user.id)
    if success:
        return {"message": "Successfully disconnected Google Calendar and deleted tokens."}
    else:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete user tokens.")


@app.get(f"{settings.API_V1_STR}/calendar/meta/list-calendars", tags=["Calendar"])
async def list_google_calendars(current_user: CurrentUser):
    # Example usage of get_decrypted_user_tokens
    tokens = get_decrypted_user_tokens(current_user.id)
    if not tokens or 'access_token' not in tokens:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="User tokens not found or invalid. Please connect Google Calendar.")

    # In Sprint 3, use tokens['access_token'] to call Google Calendar API
    return {
        "message": "Placeholder: List Google Calendars endpoint reached. Token available.",
        "user_id": current_user.id,
        "access_token_present": "access_token" in tokens,
        "access_token_expiry": tokens.get("access_token_expires_at")
    }


# --- DynamoDB Integration Placeholder ---
# You will use boto3 to interact with DynamoDB.
# Configuration for boto3 will typically use environment variables for AWS credentials
# (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN (optional))
# or an IAM role if running on EC2/ECS/Lambda.

# Example of how you might initialize a DynamoDB resource (add to a db.py file later)
# import boto3
#
# def get_dynamodb_resource():
#     if settings.AWS_DYNAMODB_ENDPOINT_URL:
#         # For local testing (e.g., DynamoDB Local)
#         dynamodb = boto3.resource('dynamodb',
#                                   region_name=settings.AWS_REGION,
#                                   endpoint_url=settings.AWS_DYNAMODB_ENDPOINT_URL)
#         print(f"Connecting to DynamoDB Local at {settings.AWS_DYNAMODB_ENDPOINT_URL}")
#     else:
#         # For AWS environment
#         dynamodb = boto3.resource('dynamodb', region_name=settings.AWS_REGION)
#         print(f"Connecting to DynamoDB in region {settings.AWS_REGION}")
#     return dynamodb
#
# # You would then use this resource to get tables:
# # dynamodb_resource = get_dynamodb_resource()
# # user_tokens_table = dynamodb_resource.Table('UserGoogleTokens') # Example table name


if __name__ == "__main__":
    import uvicorn

    # This is for local development. For production, use a process manager like Gunicorn.
    print(f"Starting Uvicorn server. OpenAPI docs at http://localhost:8000{settings.API_V1_STR}/docs")
    print("Current settings:")
    print(f"  GOOGLE_CLIENT_ID: {'SET' if settings.GOOGLE_CLIENT_ID else 'NOT SET'}")
    print(f"  GOOGLE_CLIENT_SECRET: {'SET' if settings.GOOGLE_CLIENT_SECRET else 'NOT SET'}")
    print(f"  ENCRYPTION_KEY: {'SET' if settings.ENCRYPTION_KEY else 'NOT SET'}")
    print(f"  AWS_REGION: {settings.AWS_REGION}")
    if settings.AWS_DYNAMODB_ENDPOINT_URL:
        print(f"  AWS_DYNAMODB_ENDPOINT_URL: {settings.AWS_DYNAMODB_ENDPOINT_URL}")

    uvicorn.run(app, host="0.0.0.0", port=8001)


