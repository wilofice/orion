from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

from settings_v1 import settings

logger = logging.getLogger(__name__)

# Security scheme for bearer token
bearer_scheme = HTTPBearer()


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token with the provided data and expiration.
    
    Args:
        data: Dictionary containing the payload data (e.g., user_id, email)
        expires_delta: Optional expiration time delta. Defaults to JWT_ACCESS_TOKEN_EXPIRE_MINUTES from settings
        
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Add standard JWT claims
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decode and validate a JWT access token.
    
    Args:
        token: The JWT token string to decode
        
    Returns:
        Dictionary containing the token payload
        
    Raises:
        HTTPException: If the token is invalid or expired
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        
        # Verify it's an access token
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return payload
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> Dict[str, Any]:
    """
    Dependency to get the current authenticated user from the JWT token.
    
    Args:
        credentials: The HTTP authorization credentials containing the bearer token
        
    Returns:
        Dictionary containing user information from the token
        
    Raises:
        HTTPException: If the token is invalid or expired
    """
    token = credentials.credentials
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Decode the token and extract user information
    payload = decode_access_token(token)
    
    # Extract user information from the payload
    user_info = {
        "user_id": payload.get("user_id"),
        "email": payload.get("email"),
        "google_user_id": payload.get("google_user_id"),
        "scopes": payload.get("scopes", [])
    }
    
    # Ensure we have at least a user_id
    if not user_info.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info(f"Successfully authenticated user: {user_info['user_id']}")
    return user_info


async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    """
    Legacy verify_token function for backward compatibility.
    Returns just the user_id string instead of the full user info.
    
    This function is used by existing endpoints that expect just a user_id string.
    New endpoints should use get_current_user instead.
    """
    user_info = await get_current_user(credentials)
    return user_info["user_id"]