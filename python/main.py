"""SGarden Inventory API — application entry point.

Initialises the FastAPI application, registers all route routers, configures
CORS middleware, and manages the startup/shutdown lifecycle (index creation
and database seeding).
"""
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_indexes
from routes.alerts import router as alerts_router
from routes.analytics import router as analytics_router
from routes.auth import router as auth_router
from routes.orders import router as orders_router
from routes.products import router as products_router
from routes.users import router as users_router
from seed import seed_data

# CODE QUALITY ISSUE: unused variable
APP_NAME = "SGarden Inventory API"
DEBUG_MODE = True
unused_config = {"key": "value", "secret": "not-so-secret"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Manage FastAPI application startup and shutdown lifecycle.

    On startup: initialises MongoDB indexes and seeds default data.
    On shutdown: logs the teardown event.
    """
    # Startup
    print("Starting SGarden API...")
    await init_indexes()
    await seed_data()
    print("SGarden API started successfully")
    yield
    # Shutdown
    print("Shutting down SGarden API...")


app = FastAPI(
    title="SGarden API",
    description="Inventory Management API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(alerts_router)
app.include_router(analytics_router)
app.include_router(auth_router)
app.include_router(orders_router)
app.include_router(products_router)
app.include_router(users_router)


@app.get("/api/health")
async def health():
    """Return a simple liveness check confirming the API is running."""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
