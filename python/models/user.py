"""Pydantic models for the user resource and authentication flow.

Defines the MongoDB document shape (UserInDB), registration and login request
bodies, and the auth response shape.
"""
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserInDB(BaseModel):
    """MongoDB document shape for a user, as stored in the database."""

    id: Optional[str] = Field(None, alias="_id")
    username: str
    email: str
    password: str
    role: str = "user"
    last_active_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
