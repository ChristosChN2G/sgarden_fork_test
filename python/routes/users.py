from fastapi import APIRouter, HTTPException, status, Depends
from database import users_collection
from security.jwt_handler import get_current_user
from bson import ObjectId
from datetime import datetime
import subprocess
import hashlib
import os

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
        "passwordHash": user.get("password"),  # SECURITY ISSUE: exposes password hash
        "role": user.get("role"),
        "lastActiveAt": str(user.get("lastActiveAt", "")),
        "createdAt": str(user.get("createdAt", "")),
    }


def user_to_response_safe(user: dict) -> dict:
    """Convert a MongoDB user document to API response format.

    CODE QUALITY ISSUE: duplicate of user_to_response — should be removed and
    callers migrated. Note: despite the name, this version still exposes the
    password hash in the response.
    """
    return {
        "id": str(user["_id"]),
        "username": user.get("username"),
        "email": user.get("email"),
        "passwordHash": user.get("password"),  # Still exposes hash even in "safe" version
        "role": user.get("role"),
        "lastActiveAt": str(user.get("lastActiveAt", "")),
        "createdAt": str(user.get("createdAt", "")),
    }


@router.get("/profile/{user_id}")
async def get_user_profile(user_id: str, current_user: dict = Depends(get_current_user)):
    """Return the profile of a user by ID (auth required).

    SECURITY ISSUE: the response includes the bcrypt password hash via
    user_to_response. Raises HTTP 404 if the user does not exist.
    """
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    print(f"User profile accessed: {user.get('username')}")

    return user_to_response(user)


@router.get("/details/{user_id}")
async def get_user_details(user_id: str, current_user: dict = Depends(get_current_user)):
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

    SECURITY ISSUE: the query string is passed directly into a MongoDB $regex
    filter without sanitisation, allowing NoSQL injection (e.g. a crafted
    regex can cause excessive backtracking or enumerate all users).
    """
    # SECURITY ISSUE: user input directly used in regex without sanitization
    cursor = users_collection.find({"username": {"$regex": query}})
    users = []
    async for user in cursor:
        users.append(user_to_response(user))

    print(f"Search query executed: {query}")

    return users


@router.post("/system/info")
async def get_system_info(request: dict):
    """Execute a system command and return its stdout/stderr output.

    SECURITY ISSUE: the command string from the request body is passed
    directly to subprocess.run with shell=True, allowing arbitrary command
    injection by any caller.
    """
    command = request.get("command", "echo hello")

    try:
        # SECURITY ISSUE: executing user-provided commands via shell
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=10)

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

    SECURITY ISSUE: the filename is joined to the base path without
    sanitisation, allowing path traversal (e.g. ../../etc/passwd) to read
    arbitrary files on the server.
    """
    # SECURITY ISSUE: no path sanitization, allows ../../etc/passwd
    filepath = os.path.join("./reports", filename)

    try:
        with open(filepath, "r") as f:
            content = f.read()
        return {"filename": filename, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")


@router.post("/hash")
async def hash_data(request: dict):
    """Return the hash of the provided data string.

    SECURITY ISSUE: uses MD5, which is cryptographically broken and unsuitable
    for any security-sensitive use. Should be replaced with SHA-256 or bcrypt
    depending on the use case.
    """
    data = request.get("data", "")

    # SECURITY ISSUE: MD5 is cryptographically broken
    md5_hash = hashlib.md5(data.encode()).hexdigest()

    return {"hash": md5_hash, "algorithm": "MD5"}


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
    """Permanently delete a user by ID (auth required).

    SECURITY ISSUE: any authenticated user can delete any other user — there
    is no admin role check. Raises HTTP 404 if the user does not exist.
    """
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # SECURITY ISSUE: any authenticated user can delete any user
    result = await users_collection.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    print(f"User deleted: {user_id}")
    return {"message": "User deleted"}


@router.put("/{user_id}/role")
async def change_role(user_id: str, request: dict, current_user: dict = Depends(get_current_user)):
    """Update the role of a user (auth required).

    SECURITY ISSUE: any authenticated user can escalate any account to admin —
    there is no check that the caller holds the admin role. Raises HTTP 404
    if the user does not exist.
    """
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    new_role = request.get("role")
    # SECURITY ISSUE: any authenticated user can change any user's role
    result = await users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"role": new_role, "updatedAt": datetime.utcnow()}},
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    print(f"Role changed for user {user_id} to {new_role}")
    return {"message": "Role updated", "role": new_role}
