import base64
import json
import os
import time
from typing import Optional, Dict, Any, Tuple

import boto3
import httpx
from boto3.dynamodb.types import Binary
from botocore.exceptions import ClientError
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from settings_v1 import settings
# --- Encryption Utilities ---
# AES-256 GCM uses a 12-byte (96-bit) IV by convention.
AES_GCM_IV_LENGTH_BYTES = 12


# Placeholder for DynamoDB table reference
def get_dynamodb_resource():

    if settings.AWS_DYNAMODB_ENDPOINT_URL:  # For local testing
        print(f"Connecting to DynamoDB Local at {settings.AWS_DYNAMODB_ENDPOINT_URL}")
        return boto3.resource('dynamodb',
                              region_name=settings.AWS_REGION,
                              endpoint_url=settings.AWS_DYNAMODB_ENDPOINT_URL)
    else:  # For AWS environment
        print(f"Connecting to DynamoDB in region {settings.AWS_REGION}")

        return boto3.resource('dynamodb', region_name=settings.AWS_REGION)


def create_user_tokens_table():
    dynamodb = get_dynamodb_resource()
    table_name = settings.DYNAMODB_USER_TOKENS_TABLE_NAME

    try:
        table = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {'AttributeName': 'app_user_id', 'KeyType': 'HASH'},  # Partition key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'app_user_id', 'AttributeType': 'S'},
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5,
            }
        )
        table.wait_until_exists()
        print(f"Table {table_name} created successfully.")
    except Exception as e:
        print(f"Error creating table {table_name}: {e}")

#create_user_tokens_table()

user_tokens_table = get_dynamodb_resource().Table(settings.DYNAMODB_USER_TOKENS_TABLE_NAME)


def save_user_tokens(
        app_user_id: str, access_token: str, access_token_expires_in: int,
        scopes: Optional[str] = None, refresh_token: Optional[str] = None,
        id_token_str: Optional[str] = None, existing_item: Optional[Dict[str, Any]] = None
) -> str:
    current_timestamp = int(time.time())
    access_token_expires_at = current_timestamp + access_token_expires_in
    iv_access, ct_access, tag_access = encrypt_token(access_token, settings.ENCRYPTION_KEY_BYTES)

    item_to_save = {
        'app_user_id': app_user_id,
        'encrypted_access_token': Binary(ct_access), 'iv_access_token': Binary(iv_access),
        'auth_tag_access_token': Binary(tag_access), 'access_token_expires_at': access_token_expires_at,
        'updated_at': current_timestamp,
    }
    if scopes: item_to_save['scopes'] = scopes

    if id_token_str:  # This typically only comes with the initial auth code exchange
        try:
            payload_part = id_token_str.split('.')[1]
            payload_part += '=' * (-len(payload_part) % 4)
            decoded_payload_bytes = base64.urlsafe_b64decode(payload_part.encode('utf-8'))
            decoded_payload = json.loads(decoded_payload_bytes.decode('utf-8'))
            google_user_id = decoded_payload.get('sub')
            if google_user_id: item_to_save['google_user_id'] = google_user_id
        except Exception as e:
            print(f"Warning: Could not decode/extract 'sub' from ID token: {e}")
    elif existing_item and 'google_user_id' in existing_item:  # Preserve existing google_user_id if not new id_token
        item_to_save['google_user_id'] = existing_item['google_user_id']

    if refresh_token:  # If a new refresh token is provided (e.g. initial exchange, or if Google rotates it)
        iv_refresh, ct_refresh, tag_refresh = encrypt_token(refresh_token, settings.ENCRYPTION_KEY_BYTES)
        item_to_save['encrypted_refresh_token'] = Binary(ct_refresh)
        item_to_save['iv_refresh_token'] = Binary(iv_refresh)
        item_to_save['auth_tag_refresh_token'] = Binary(tag_refresh)
    elif existing_item and 'encrypted_refresh_token' in existing_item:  # Preserve existing refresh token if not new one
        item_to_save['encrypted_refresh_token'] = existing_item['encrypted_refresh_token']
        item_to_save['iv_refresh_token'] = existing_item['iv_refresh_token']
        item_to_save['auth_tag_refresh_token'] = existing_item['auth_tag_refresh_token']

    try:
        if existing_item and 'created_at' in existing_item:
            item_to_save['created_at'] = existing_item['created_at']  # Preserve original created_at
        elif not existing_item:  # Truly new item
            item_to_save['created_at'] = current_timestamp

        user_tokens_table.put_item(Item=item_to_save)
        print(f"Successfully saved tokens for app_user_id: {app_user_id}")
        return "success"
    except ClientError as e:
        print(f"Error saving tokens to DynamoDB for {app_user_id}: {e.response['Error']['Message']}")
        return f"Error saving tokens to DynamoDB for {app_user_id}: {e.response['Error']['Message']}"
    except Exception as e:
        print(f"An unexpected error occurred during token save: {e}")
        return f"An unexpected error occurred during token save: {e}"
    return "failed"


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


def get_user_tokens_raw(app_user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves the raw token item from DynamoDB."""
    try:
        response = user_tokens_table.get_item(Key={'app_user_id': app_user_id})
        return response.get('Item')
    except ClientError as e:
        print(f"Error retrieving raw tokens from DynamoDB for {app_user_id}: {e.response['Error']['Message']}")
        return None


async def refresh_google_access_token(app_user_id: str) -> Optional[str]:
    """
    Refreshes a Google access token using a stored refresh token.
    Updates the stored tokens in DynamoDB if successful.
    Deletes tokens if the refresh token is invalid.

    Returns:
        The new access token if successful, None otherwise.
    """
    print(f"Task 3.1: Attempting to refresh Google access token for app_user_id: {app_user_id}")

    # Get the raw stored item to preserve fields and get encrypted refresh token
    stored_item_raw = get_user_tokens_raw(app_user_id)
    if not stored_item_raw or 'encrypted_refresh_token' not in stored_item_raw:
        print(f"No refresh token found for app_user_id: {app_user_id}. Cannot refresh.")
        return None

    try:
        # Decrypt only the refresh token for this operation
        iv_refresh = bytes(stored_item_raw['iv_refresh_token'])
        ct_refresh = bytes(stored_item_raw['encrypted_refresh_token'])
        tag_refresh = bytes(stored_item_raw['auth_tag_refresh_token'])
        decrypted_refresh_token = decrypt_token(iv_refresh, ct_refresh, tag_refresh, settings.ENCRYPTION_KEY_BYTES)
    except InvalidTag:
        print(f"ERROR: Failed to decrypt stored refresh token for {app_user_id}. Deleting tokens.")
        delete_user_tokens(app_user_id)
        return None
    except Exception as e:
        print(f"ERROR: Unexpected error decrypting stored refresh token for {app_user_id}: {e}. Deleting tokens.")
        delete_user_tokens(app_user_id)
        return None

    refresh_request_data = {
        "client_id": settings.GOOGLE_CLIENT_ID,  # Using mobile's client_id
        # No client_secret, consistent with user's current working setup
        "refresh_token": decrypted_refresh_token,
        "grant_type": "refresh_token",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient() as client:
        try:
            print(f"Task 3.1: Requesting new access token from Google for {app_user_id}...")
            response = await client.post(settings.GOOGLE_TOKEN_URL, data=refresh_request_data, headers=headers)

            print(f"DEBUG: Google Refresh Response Status Code: {response.status_code}")
            print(f"DEBUG: Google Refresh Response Raw Text: {response.text}")
            response.raise_for_status()

            new_token_data: Dict[str, Any] = response.json()
            new_access_token = new_token_data.get("access_token")
            new_expires_in = new_token_data.get("expires_in")
            # Google might sometimes return a new id_token or even a new refresh_token (if rotation is on)
            # For simplicity, we'll primarily focus on the new access_token here.
            # The 'scopes' usually don't change on refresh.

            if not new_access_token or new_expires_in is None:
                print(f"ERROR: New access token or expires_in missing from Google refresh response for {app_user_id}.")
                # Potentially delete tokens if response is malformed but not an outright auth error
                return None

            print(f"Task 3.1: Successfully refreshed access token for {app_user_id}.")

            # Save the updated tokens. Pass the original refresh token if not rotated,
            # or the new one if Google sends it (new_token_data.get("refresh_token")).
            # For this example, we assume the refresh token in stored_item_raw is still valid
            # unless Google explicitly sends a new one.
            # We also pass the existing_item to preserve fields like created_at and google_user_id.
            save_success = save_user_tokens(
                app_user_id=app_user_id,
                access_token=new_access_token,
                access_token_expires_in=int(new_expires_in),
                scopes=new_token_data.get("scope", stored_item_raw.get("scopes")),
                # Use new scopes if provided, else old
                refresh_token=new_token_data.get("refresh_token"),  # Use new refresh token if provided by Google
                id_token_str=new_token_data.get("id_token"),  # Use new id_token if provided
                existing_item=stored_item_raw  # Pass the original raw item to help preserve fields
            )

            if not save_success == "success":
                print(f"ERROR: Failed to save refreshed tokens for {app_user_id}. {save_success}")
                return None  # Or raise an exception

            return new_token_data

        except httpx.HTTPStatusError as e:
            error_details_text = e.response.text
            print(
                f"HTTP error from Google during token refresh for {app_user_id}: {e.response.status_code} - {error_details_text}")

            # If 'invalid_grant', the refresh token is no longer valid. Delete stored tokens.
            if e.response.status_code == 400 or e.response.status_code == 401:  # Common for auth errors
                try:
                    error_json = e.response.json()
                    if error_json.get("error") == "invalid_grant":
                        print(f"Refresh token for {app_user_id} is invalid. Deleting stored tokens.")
                        delete_user_tokens(app_user_id)
                except Exception:  # If response isn't JSON
                    pass  # Already logged the text
            return None
        except Exception as e:
            print(f"Unexpected error during token refresh for {app_user_id}: {e}")
            return None


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
