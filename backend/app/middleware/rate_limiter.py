"""
Rate limiting middleware
"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import REDIS_CLIENT
import time
import logging

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware using Redis.
    Implements a sliding window rate limiter.
    """
    
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.window_size = 60  # seconds
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        # Get client identifier (IP or user ID from token)
        client_id = self._get_client_id(request)
        
        if not REDIS_CLIENT:
            # If Redis is not available, skip rate limiting
            logger.warning("Redis not available, skipping rate limiting")
            return await call_next(request)
        
        # Check rate limit
        if not self._check_rate_limit(client_id):
            logger.warning(f"Rate limit exceeded for client: {client_id}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded. Please try again later.",
                    "retry_after": 60
                }
            )
        
        response = await call_next(request)
        return response
    
    def _get_client_id(self, request: Request) -> str:
        """Get client identifier from request."""
        # Try to get user ID from auth header (if implemented)
        # For now, use IP address
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0]
        return request.client.host if request.client else "unknown"
    
    def _check_rate_limit(self, client_id: str) -> bool:
        """
        Check if client has exceeded rate limit using sliding window.
        
        Args:
            client_id: Client identifier
            
        Returns:
            True if within limit, False if exceeded
        """
        try:
            key = f"rate_limit:{client_id}"
            current_time = time.time()
            window_start = current_time - self.window_size
            
            # Remove old entries
            REDIS_CLIENT.zremrangebyscore(key, 0, window_start)
            
            # Count requests in current window
            request_count = REDIS_CLIENT.zcard(key)
            
            if request_count >= self.requests_per_minute:
                return False
            
            # Add current request
            REDIS_CLIENT.zadd(key, {str(current_time): current_time})
            REDIS_CLIENT.expire(key, self.window_size)
            
            return True
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            # On error, allow the request (fail open)
            return True
