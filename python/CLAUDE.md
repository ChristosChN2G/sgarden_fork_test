# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This is the Python (FastAPI) implementation of the SGarden Inventory API. An equivalent Java (Spring Boot) implementation lives in `../java/`. Both share the same MongoDB schema and expose identical REST endpoints.

## Build & Run

All commands run from the `python/` directory:

```bash
# Install dependencies
pip install -r requirements.txt

# Run (starts on port 4000, with auto-reload)
python main.py

# Or with uvicorn directly
uvicorn main:app --reload --port 4000
```

**Environment variables** (read from `../.env` or environment):
- `DATABASE_URL` — MongoDB URI (default: `mongodb://localhost:27017/sgarden`)
- `PORT` — server port (default: `4000`)
- `SERVER_SECRET` — JWT signing secret (default: `sgarden-secret-key`)

On startup, `seed_data()` (called via FastAPI `lifespan`) inserts two users (`admin/admin123`, `user/user1234`) and 15 sample products if the collections are empty.

## Architecture

FastAPI + Motor (async MongoDB driver) + Pydantic v2. No service layer — business logic lives directly in route handlers:

```
routes/ → database.py → MongoDB
```

- `routes/` — `auth.py`, `products.py`, `users.py`; each file registers an `APIRouter` mounted at `/api/<resource>`
- `models/` — Pydantic models split into DB document shapes (`*InDB`) and request/response shapes (`*Request`, `*Response`)
- `security/jwt_handler.py` — `create_token`, `decode_token`, `get_current_user` FastAPI dependency (reads `Authorization: Bearer`)
- `database.py` — Motor client singleton; exports `users_collection`, `products_collection`, `db`
- `config.py` — `pydantic-settings` `Settings` class; populates from env vars or `../.env`
- `seed.py` — standalone `seed_data()` coroutine, called at startup

## Auth Flow

Client POSTs to `/api/auth/login` → receives JWT (24h TTL) → sends as `Authorization: Bearer <token>`.

**Protected endpoints:** `POST/PUT/DELETE /api/products/**` and user mutation endpoints (`DELETE /api/users/{id}`, `PUT /api/users/{id}/role`) require authentication via `Depends(get_current_user)`. All GET product endpoints, `/api/auth/*`, `/api/health`, and user read endpoints are public.

## Known Code Issues

This codebase intentionally contains vulnerabilities and code quality issues for workshop/analysis purposes.

**Security vulnerabilities:**
- `routes/users.py search_users()` — NoSQL injection: user input passed directly into MongoDB `$regex` without sanitization
- `routes/users.py get_system_info()` — command injection: `subprocess.run(shell=True)` with unsanitized user-supplied command string
- `routes/users.py download_report()` — path traversal: `os.path.join("./reports", filename)` with no sanitization (allows `../../etc/passwd`)
- `routes/users.py hash_data()` — weak crypto: MD5 via `hashlib.md5`
- `routes/users.py` profile/details endpoints — expose `passwordHash` field in every user response
- Missing authorization: any authenticated user can delete users or escalate roles (`delete_user`, `change_role` have no admin check)

**Code quality:**
- Duplicate functions: `register`/`register_user` (auth), `product_to_response`/`format_product` (products), `get_current_user`/`get_current_user_deprecated` (jwt_handler), `user_to_response`/`user_to_response_safe` (users)
- Duplicate model classes: every model has a `*V2` copy (`ProductInDBV2`, `RegisterRequestV2`, etc.) that is identical to the original
- Unused module-level variables throughout (`auth_version`, `service_name`, `API_VERSION`, `token_cache`, `unused_config`, etc.)
- High cyclomatic complexity in `advanced_search()`: deeply nested `if/else` tree that loads all users into memory then filters in Python rather than pushing filters to MongoDB
