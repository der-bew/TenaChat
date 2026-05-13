# app/config.py
import logging
import os
import sys
from typing import Optional

import redis
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

# Define globals here (they start as None until load_config())
SUPABASE_URL: Optional[str] = None
SUPABASE_KEY: Optional[str] = None
OPENAI_API_KEY: Optional[str] = None
OPENROUTER_API_KEY: Optional[str] = None
OPENROUTER_BASE_URL: Optional[str] = None
SERPER_API_KEY: Optional[str] = None
GOOGLE_API_KEY: Optional[str] = None
TAVILY_API_KEY: Optional[str] = None
REDIS_CLIENT = None  # Will be set to redis client
CORS_ORIGINS: list = []
ENVIRONMENT: str = "development"


def validate_required_env_vars():
    """Validate that all required environment variables are set."""
    required_vars = {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_KEY": SUPABASE_KEY,
        "OPENAI_API_KEY": OPENAI_API_KEY,
    }

    missing_vars = [var for var, value in required_vars.items() if not value]

    if missing_vars:
        error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if not OPENROUTER_API_KEY:
        logger.warning(
            "OPENROUTER_API_KEY is not set. Text chat will use the legacy OpenAI model instead of the configured OpenRouter primary/fallback chain."
        )

    if not SERPER_API_KEY:
        logger.warning(
            "SERPER_API_KEY is not set. Web search will be unavailable until it is configured."
        )

    logger.info("Required environment variables are set")


def load_config():
    """Load and validate configuration from environment variables."""
    global \
        SUPABASE_URL, \
        SUPABASE_KEY, \
        OPENAI_API_KEY, \
        OPENROUTER_API_KEY, \
        OPENROUTER_BASE_URL, \
        SERPER_API_KEY, \
        GOOGLE_API_KEY, \
        TAVILY_API_KEY, \
        REDIS_CLIENT, \
        CORS_ORIGINS, \
        ENVIRONMENT

    # Load environment variables
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    OPENROUTER_BASE_URL = os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    SERPER_API_KEY = os.getenv("SERPER_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    TAVILY_API_KEY = SERPER_API_KEY or os.getenv("TAVILY_API_KEY")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

    # Validate required variables
    validate_required_env_vars()

    # Configure CORS origins based on environment
    cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    CORS_ORIGINS = [origin.strip() for origin in cors_origins_str.split(",")]
    logger.info(f"CORS origins configured: {CORS_ORIGINS}")

    # Initialize Redis with error handling
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        REDIS_CLIENT = redis.from_url(REDIS_URL, decode_responses=True)
        # Test connection
        REDIS_CLIENT.ping()
        logger.info(f"Redis connected successfully at {REDIS_URL}")
    except redis.ConnectionError as e:
        logger.error(f"Failed to connect to Redis at {REDIS_URL}: {e}")
        logger.warning("Application will run without caching")
        REDIS_CLIENT = None
    except Exception as e:
        logger.error(f"Unexpected error connecting to Redis: {e}")
        REDIS_CLIENT = None


# Load configuration on module import
try:
    load_config()
except ValueError as e:
    logger.critical(f"Configuration error: {e}")
    sys.exit(1)
