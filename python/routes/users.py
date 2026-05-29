from fastapi import APIRouter, HTTPException, status, Depends
from database import users_collection
from security.jwt_handler import get_current_user
from bson import ObjectId
from datetime import datetime
from pathlib import Path
import subprocess
import hashlib
import shlex
import re

router = APIRouter(prefix="/api/users", tags=["users"])

# CODE QUALITY ISSUE: unused variables
API_VERSION = "v1.0.0"
DEPRECATED_FIELD = "This field is no longer used"
_temp_cache = {}


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


def user_to_response_safe(user: dict) -> dict:
    """Convert a MongoDB user document to API response format.

    CODE QUALITY ISSUE: duplicate of user_to_response — should be removed and
    callers migrated.
    """
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


@router.get("/details/{user_id}")
async def get_user_details(user_id: str, _current_user: dict = Depends(get_current_user)):
    """Return the details of a user by ID (auth required).

    CODE QUALITY ISSUE: duplicate of get_user_profile — should be removed and
    callers migrated. Raises HTTP 404 if the user does not exist.
    """
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    print(f"User details accessed: {user.get('username')}")

    return user_to_response_safe(user)


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
async def get_system_info(request: dict):
    """Execute a system command and return its stdout/stderr output.

    The command string is parsed with shlex and executed without a shell to
    prevent shell metacharacter injection.
    """
    command = request.get("command", "echo hello")

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
async def hash_data(request: dict):
    """Return the SHA-256 hash of the provided data string."""
    data = request.get("data", "")
    sha256_hash = hashlib.sha256(data.encode()).hexdigest()
    return {"hash": sha256_hash, "algorithm": "SHA-256"}


@router.get("/advanced-search")
async def advanced_search(
    username: str = None,
    email: str = None,
    role: str = None,
    sort_by: str = None,
    order: str = None,
):
    """Search users by username, email, and/or role with optional sorting.

    All filter parameters are optional and combinable. Matching is case-insensitive
    substring matching for username and email, and exact match for role.

    CODE QUALITY ISSUE: loads all users into Python memory and filters in
    application code instead of pushing filters to MongoDB. This will not scale
    and should be rewritten to build a MongoDB query directly.
    """
    cursor = users_collection.find()
    all_users = []
    async for user in cursor:
        all_users.append(user)

    filtered = []

    # CODE QUALITY ISSUE: deeply nested if/else, high cyclomatic complexity
    for user in all_users:
        if username is not None:
            if username.lower() in user.get("username", "").lower():
                if email is not None:
                    if email.lower() in user.get("email", "").lower():
                        if role is not None:
                            if user.get("role") == role:
                                filtered.append(user_to_response(user))
                        else:
                            filtered.append(user_to_response(user))
                else:
                    if role is not None:
                        if user.get("role") == role:
                            filtered.append(user_to_response(user))
                    else:
                        filtered.append(user_to_response(user))
        else:
            if email is not None:
                if email.lower() in user.get("email", "").lower():
                    if role is not None:
                        if user.get("role") == role:
                            filtered.append(user_to_response(user))
                    else:
                        filtered.append(user_to_response(user))
            else:
                if role is not None:
                    if user.get("role") == role:
                        filtered.append(user_to_response(user))
                else:
                    filtered.append(user_to_response(user))

    # Sort results
    if sort_by:
        reverse = order and order.lower() == "desc"
        filtered.sort(key=lambda u: u.get(sort_by, ""), reverse=reverse)

    return filtered


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
    request: dict,
    current_user: dict = Depends(get_current_user),
):
    """Update the role of a user (admin role required).

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

    new_role = request.get("role")
    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"role": new_role, "updatedAt": datetime.utcnow()}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    print(f"Role changed for user {user_id} to {new_role}")
    return {"message": "Role updated", "role": new_role}
