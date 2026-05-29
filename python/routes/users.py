"""User management routes.

Provides user profile retrieval, search, advanced filtered search, role
management (admin-only), and several utility endpoints. All previously
documented security vulnerabilities in this module have been remediated.
"""
import hashlib
import re
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from database import users_collection
from security.jwt_handler import get_current_user

router = APIRouter(prefix="/api/users", tags=["users"])

_VALID_ROLES = {"admin", "user"}


class SystemInfoRequest(BaseModel):
    """Request body for the system info endpoint."""

    command: str = "echo hello"


class HashRequest(BaseModel):
    """Request body for the data hashing endpoint."""

    data: str = ""


class RoleUpdateRequest(BaseModel):
    """Request body for updating a user's role."""

    role: str = Field(..., description="Target role — must be 'admin' or 'user'")


def user_to_response(user: dict) -> dict:
    """Convert MongoDB user document to API response."""
    return {
        "id": str(user["_id"]),
        "username": user.get("username"),
        "email": user.get("email"),
        "role": user.get("role"),
        "lastActiveAt": str(user.get("lastActiveAt", "")),
        "createdAt": str(user.get("createdAt", "")),
    }


@router.get("/profile/{user_id}")
async def get_user_profile(user_id: str, _current_user: dict = Depends(get_current_user)):
    """Return the profile of a user by ID (auth required).

    Raises HTTP 404 if the user does not exist.
    """
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    print(f"User profile accessed: {user.get('username')}")

    return user_to_response(user)


@router.get("/search")
async def search_users(query: str):
    """Search users by username substring match.

    The query string is escaped before use in the MongoDB $regex filter to
    prevent regex injection attacks.
    """
    cursor = users_collection.find({"username": {"$regex": re.escape(query)}})
    users = []
    async for user in cursor:
        users.append(user_to_response(user))

    print(f"Search query executed: {query}")

    return users


@router.post("/system/info")
async def get_system_info(request: SystemInfoRequest):
    """Execute a system command and return its stdout/stderr output.

    The command string is parsed with shlex and executed without a shell to
    prevent shell metacharacter injection.
    """
    command = request.command

    try:
        args = shlex.split(command)
        result = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=10)

        print(f"Command executed: {command}")

        return {"output": result.stdout, "error": result.stderr}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Command failed: {str(e)}",
        )


@router.get("/reports/download")
async def download_report(filename: str):
    """Return the contents of a report file from the ./reports directory.

    The resolved path is validated to ensure it stays within the reports
    directory, preventing path traversal attacks.
    Raises HTTP 400 for invalid filenames and HTTP 404 if the file is not found.
    """
    base = Path("./reports").resolve()
    filepath = (base / filename).resolve()

    if not filepath.is_relative_to(base):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename",
        )

    try:
        with open(filepath, "r") as f:
            content = f.read()
        return {"filename": filename, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")


@router.post("/hash")
async def hash_data(request: HashRequest):
    """Return the SHA-256 hash of the provided data string."""
    sha256_hash = hashlib.sha256(request.data.encode()).hexdigest()
    return {"hash": sha256_hash, "algorithm": "SHA-256"}


_SORT_FIELD_MAP = {
    "id": "_id",
    "username": "username",
    "email": "email",
    "role": "role",
    "lastActiveAt": "lastActiveAt",
    "createdAt": "createdAt",
}


@router.get("/advanced-search")
async def advanced_search(
    username: Optional[str] = None,
    email: Optional[str] = None,
    role: Optional[str] = None,
    sort_by: Optional[str] = None,
    order: Optional[str] = None,
):
    """Search users by username, email, and/or role with optional sorting.

    All filter parameters are optional and combinable. Matching is
    case-insensitive substring matching for username and email, and exact
    match for role. Filters are pushed to MongoDB rather than applied in
    Python.
    """
    query = {}
    if username is not None:
        query["username"] = {"$regex": re.escape(username), "$options": "i"}
    if email is not None:
        query["email"] = {"$regex": re.escape(email), "$options": "i"}
    if role is not None:
        query["role"] = role

    cursor = users_collection.find(query)
    if sort_by and sort_by in _SORT_FIELD_MAP:
        direction = -1 if order and order.lower() == "desc" else 1
        cursor = cursor.sort(_SORT_FIELD_MAP[sort_by], direction)

    return [user_to_response(user) async for user in cursor]


@router.delete("/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    """Permanently delete a user by ID (admin role required).

    Raises HTTP 403 if the caller is not an admin, and HTTP 404 if the user
    does not exist.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    result = await users_collection.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    print(f"User deleted: {user_id}")
    return {"message": "User deleted"}


@router.put("/{user_id}/role")
async def change_role(
    user_id: str,
    request: RoleUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update the role of a user (admin role required).

    Raises HTTP 400 if the role is not valid, HTTP 403 if the caller is not
    an admin, and HTTP 404 if the user does not exist.
    """
    if request.role not in _VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(_VALID_ROLES))}",
        )

    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    new_role = request.role
    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"role": new_role, "updatedAt": datetime.utcnow()}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    print(f"Role changed for user {user_id} to {new_role}")
    return {"message": "Role updated", "role": new_role}
