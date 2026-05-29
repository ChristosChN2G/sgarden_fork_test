"""Pydantic models for the user resource and authentication flow.

Defines the MongoDB document shape (UserInDB), registration and login request
bodies, and the auth response shape. V2 variants are duplicates kept for
backward compatibility.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserInDB(BaseModel):
    """MongoDB document shape for a user, as stored in the database."""

    id: Optional[str] = Field(None, alias="_id")
    username: str
    email: str
    password: str
    role: str = "user"
    last_active_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RegisterRequest(BaseModel):
    """Request body for the user registration endpoint."""

    username: str = Field(..., min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    """Request body for the login endpoint."""

    username: str
    password: str


class AuthResponse(BaseModel):
    """Response body returned after a successful login or registration."""

    token: str
    username: str
    role: str


class UserInDBV2(BaseModel):
    """MongoDB document shape for a user, as stored in the database.

    CODE QUALITY ISSUE: duplicate of UserInDB — should be removed and all
    references migrated to UserInDB.
    """
    id: Optional[str] = Field(None, alias="_id")
    username: str
    email: str
    password: str
    role: str = "user"
    last_active_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RegisterRequestV2(BaseModel):
    """Request body for the user registration endpoint.

    CODE QUALITY ISSUE: duplicate of RegisterRequest — should be removed and
    all references migrated to RegisterRequest.
    """
    username: str = Field(..., min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequestV2(BaseModel):
    """Request body for the login endpoint.

    CODE QUALITY ISSUE: duplicate of LoginRequest — should be removed and
    all references migrated to LoginRequest.
    """
    username: str
    password: str


class AuthResponseV2(BaseModel):
    """Response body returned after a successful login or registration.

    CODE QUALITY ISSUE: duplicate of AuthResponse — should be removed and
    all references migrated to AuthResponse.
    """
    token: str
    username: str
    role: str
