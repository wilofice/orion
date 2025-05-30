from typing import Optional

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Calendar Events Manager Backend"
    API_V1_STR: str = "/Prod"
    GOOGLE_CLIENT_ID_IOS: str  # This is now the mobile app's client ID as per user's findings
    GOOGLE_CLIENT_ID_ANDROID: str  # This is now the mobile app's client ID as per user's findings
    # GOOGLE_CLIENT_SECRET is no longer used in token exchange as per user's findings
    AWS_REGION: str = "eu-north-1"
    DYNAMODB_USER_TOKENS_TABLE_NAME: str = "UserGoogleTokens"
    DYNAMODB_CHAT_SESSIONS_TABLE_NAME: str = "ChatSessions"
    DYNAMODB_USER_PREFERENCES_TABLE_NAME: str = "UserPreferences"
    DYNAMODB_USER_TASKS_TABLE_NAME: str = "UserTasks"
    DYNAMODB_USER_EMAIL_MAPPING_TABLE_NAME: str = "UserEmailMapping"
    AWS_DYNAMODB_ENDPOINT_URL: Optional[str] = None  # Optional for local development/testing

    # ENCRYPTION_KEY must be a 32-byte (256-bit) key.
    # It should be hex-encoded in the .env file (64 hex characters).
    ENCRYPTION_KEY_HEX: str  # Renamed to clarify it's hex encoded in .env

    JWT_SECRET_KEY: str = "your-super-secret-jwt-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    GOOGLE_TOKEN_URL: str = "https://oauth2.googleapis.com/token"
    GEMINI_API_KEY: str = "your-gemini-api-key"  # Ensure this is set in your .env file

    # Derived property for the actual encryption key bytes
    @property
    def ENCRYPTION_KEY_BYTES(self) -> bytes:
        try:
            return bytes.fromhex(self.ENCRYPTION_KEY_HEX)
        except ValueError:
            raise ValueError("ENCRYPTION_KEY_HEX in .env must be a valid 64-character hex string (32 bytes).")

    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()