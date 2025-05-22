from typing import Optional

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI Calendar Events Manager Backend"
    API_V1_STR: str = "/api/v1"
    GOOGLE_CLIENT_ID: str  # This is now the mobile app's client ID as per user's findings
    # GOOGLE_CLIENT_SECRET is no longer used in token exchange as per user's findings
    AWS_REGION: str = "us-east-1"
    AWS_DYNAMODB_ENDPOINT_URL: Optional[str] = None

    # ENCRYPTION_KEY must be a 32-byte (256-bit) key.
    # It should be hex-encoded in the .env file (64 hex characters).
    ENCRYPTION_KEY_HEX: str  # Renamed to clarify it's hex encoded in .env

    JWT_SECRET_KEY: str = "your-super-secret-jwt-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    GOOGLE_TOKEN_URL: str = "https://oauth2.googleapis.com/token"

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