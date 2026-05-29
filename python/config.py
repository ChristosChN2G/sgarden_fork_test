import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env file.

    All fields can be overridden by setting the corresponding environment
    variable (e.g. DATABASE_URL, PORT, SERVER_SECRET, JWT_EXPIRATION_HOURS).
    """

    database_url: str = "mongodb://localhost:27017/sgarden"
    port: int = 4000
    server_secret: str = "sgarden-secret-key"
    jwt_expiration_hours: int = 24

    class Config:
        """Pydantic settings configuration — resolves values from ../.env."""

        env_file = "../.env"
        extra = "ignore"


settings = Settings()
