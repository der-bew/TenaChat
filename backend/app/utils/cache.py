"""
Caching utilities with secure key generation
"""

import hashlib
import json
import logging
import secrets
from typing import Any, Dict, Optional, cast

from app.config import REDIS_CLIENT

logger = logging.getLogger(__name__)

# Generate a secure salt for cache keys (should be stored securely in production)
CACHE_SALT = secrets.token_hex(32)


def _get_redis_client() -> Any:
    """Return the configured Redis client."""
    return REDIS_CLIENT


def generate_cache_key(
    user_id: str, message: str, conversation_id: Optional[str] = None
) -> str:
    """
    Generate a secure cache key using SHA-256 with salt.

    Args:
        user_id: User identifier
        message: User message
        conversation_id: Optional conversation identifier to keep caches scoped per conversation

    Returns:
        Secure cache key
    """
    # Combine user_id, conversation_id, message, and salt
    conversation_scope = conversation_id or "no_conversation"
    data = f"{user_id}:{conversation_scope}:{message}:{CACHE_SALT}"
    # Use SHA-256 instead of MD5
    return hashlib.sha256(data.encode()).hexdigest()


def get_cached_response(cache_key: str) -> Optional[str]:
    """
    Get cached response if available.

    Args:
        cache_key: Cache key to lookup

    Returns:
        Cached response or None
    """
    client = _get_redis_client()
    if not client:
        return None

    try:
        cached = cast(Optional[str], client.get(cache_key))
        if cached:
            logger.info(f"Cache hit for key: {cache_key[:16]}...")
            return cached
        return None
    except Exception as e:
        logger.error(f"Error getting cached response: {e}")
        return None


def set_cached_response(cache_key: str, response: str, ttl: int = 86400) -> bool:
    """
    Cache a response with TTL.

    Args:
        cache_key: Cache key
        response: Response to cache
        ttl: Time to live in seconds (default 24 hours)

    Returns:
        True if successful, False otherwise
    """
    client = _get_redis_client()
    if not client:
        return False

    try:
        client.set(cache_key, response, ex=ttl)
        logger.info(f"Cached response for key: {cache_key[:16]}...")
        return True
    except Exception as e:
        logger.error(f"Error caching response: {e}")
        return False


def invalidate_cache(pattern: str) -> int:
    """
    Invalidate cache entries matching a pattern.

    Args:
        pattern: Redis key pattern (e.g., "user:123:*")

    Returns:
        Number of keys deleted
    """
    client = _get_redis_client()
    if not client:
        return 0

    try:
        keys = list(cast(Any, client.keys(pattern)))
        if keys:
            deleted = int(cast(Any, client.delete(*keys)))
            logger.info(f"Invalidated {deleted} cache entries matching: {pattern}")
            return deleted
        return 0
    except Exception as e:
        logger.error(f"Error invalidating cache: {e}")
        return 0


async def save_anonymous_session(
    user_id: str,
    conversation_id: Optional[str] = None,
    user_message: Optional[str] = None,
    ai_response: Optional[str] = None,
) -> bool:
    """
    Save anonymous user session data to Redis.

    Args:
        user_id: Anonymous user ID
        conversation_id: Optional conversation ID
        user_message: Optional user message
        ai_response: Optional AI response

    Returns:
        True if successful, False otherwise
    """
    client = _get_redis_client()
    if not client:
        return False

    try:
        key = f"anon_session:{user_id}"

        # Get existing session or create new
        existing = cast(Optional[str], cast(Any, client.get(key)))
        session_data: Dict[str, Any] = (
            json.loads(existing)
            if existing
            else {"conversations": {}, "created_at": secrets.token_hex(8)}
        )

        # Add conversation data if provided
        if conversation_id and user_message and ai_response:
            if conversation_id not in session_data["conversations"]:
                session_data["conversations"][conversation_id] = []

            session_data["conversations"][conversation_id].append(
                {"user": user_message, "assistant": ai_response}
            )

        # Store with 7-day TTL
        client.setex(key, 7 * 24 * 3600, json.dumps(session_data))
        logger.info(f"Saved anonymous session for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving anonymous session: {e}")
        return False


async def get_anonymous_session(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve anonymous user session data from Redis.

    Args:
        user_id: Anonymous user ID

    Returns:
        Session data or None
    """
    client = _get_redis_client()
    if not client:
        return None

    try:
        key = f"anon_session:{user_id}"
        data = cast(Optional[str], cast(Any, client.get(key)))
        return json.loads(data) if data else None
    except Exception as e:
        logger.error(f"Error getting anonymous session: {e}")
        return None


async def migrate_anonymous_to_authenticated(
    anonymous_id: str, authenticated_user_id: str
) -> bool:
    """
    Migrate anonymous session data to authenticated user.

    Args:
        anonymous_id: Anonymous session ID
        authenticated_user_id: Authenticated user ID

    Returns:
        True if successful, False otherwise
    """
    client = _get_redis_client()
    if not client:
        return False

    try:
        # Get anonymous session
        anon_session = await get_anonymous_session(anonymous_id)
        if not anon_session:
            return False

        # Get or create authenticated user session
        auth_key = f"user_session:{authenticated_user_id}"
        existing = cast(Optional[str], cast(Any, client.get(auth_key)))
        auth_session: Dict[str, Any] = (
            json.loads(existing) if existing else {"conversations": {}}
        )

        # Merge conversations
        for convo_id, messages in anon_session.get("conversations", {}).items():
            if convo_id not in auth_session["conversations"]:
                auth_session["conversations"][convo_id] = []
            auth_session["conversations"][convo_id].extend(messages)

        # Save merged session
        client.setex(auth_key, 30 * 24 * 3600, json.dumps(auth_session))

        # Delete anonymous session
        client.delete(f"anon_session:{anonymous_id}")

        logger.info(
            f"Migrated anonymous session {anonymous_id} to user {authenticated_user_id}"
        )
        return True
    except Exception as e:
        logger.error(f"Error migrating anonymous session: {e}")
        return False
