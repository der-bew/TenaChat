import logging
from typing import Optional

from app.config import SUPABASE_KEY, SUPABASE_URL
from supabase import Client, create_client

logger = logging.getLogger(__name__)


def get_supabase_client(access_token: Optional[str] = None) -> Client:
    """Initialize and return a Supabase client.

    When an ``access_token`` is provided, PostgREST requests are executed in the
    context of that authenticated user so row-level security policies can use
    ``auth.uid()`` correctly.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase URL and KEY must be configured")

    try:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        if access_token:
            client.postgrest.auth(access_token)
        logger.info(
            "Supabase client initialized successfully%s",
            " with request auth" if access_token else "",
        )
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        raise


# Initialize the global client for auth/admin-like operations that do not need
# request-scoped row-level security context.
supabase: Client = get_supabase_client()
