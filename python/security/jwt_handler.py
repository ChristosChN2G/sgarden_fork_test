from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import settings
from database import users_collection
from bson import ObjectId

security = HTTPBearer(auto_error=False)

SECRET_KEY = settings.server_secret
ALGORITHM = "HS256"
EXPIRATION_HOURS = settings.jwt_expiration_hours

# CODE QUALITY ISSUE: unused variable
token_cache = {}


def create_token(user_id: str, username: str, role: str) -> str:
    """Create a signed HS256 JWT containing user identity and role claims.

    The token is valid for EXPIRATION_HOURS hours from the time of creation.
    """
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(hours=EXPIRATION_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT, returning its payload as a dict.

    Raises HTTP 401 if the token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """FastAPI dependency that resolves the authenticated user from a Bearer token.

    Validates the token, looks up the user in the database, and returns the
    user document with the MongoDB _id converted to a string.
    Raises HTTP 401 if the token is missing, invalid, or the user no longer exists.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")

    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    user["_id"] = str(user["_id"])
    return user


async def get_current_user_deprecated(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Resolve the authenticated user from a Bearer token.

    CODE QUALITY ISSUE: duplicate of get_current_user — kept for backward
    compatibility but should be removed and callers migrated to get_current_user.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    payload = decode_token(credentials.credentials)
    user_id = payload.get("sub")

    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    user["_id"] = str(user["_id"])
    return user


async def get_optional_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Returns user if authenticated, None otherwise."""
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        user_id = payload.get("sub")
        user = await users_collection.find_one({"_id": ObjectId(user_id)})
        if user:
            user["_id"] = str(user["_id"])
        return user
    except Exception:
        return None
