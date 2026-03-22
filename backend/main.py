"""
This is the main entry point for the Ethiopian Women Health Chatbot API.
version: 1.0.0
author: Derbew Felasman
"""

import logging

import uvicorn
from app.config import CORS_ORIGINS, ENVIRONMENT
from app.middleware.rate_limiter import RateLimitMiddleware
from app.routers import auth, chat, conversations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TenaChat",
    description="A chatbot for Ethiopian women's health",
    version="1.0.0",
    docs_url="/docs" if ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if ENVIRONMENT == "development" else None,
)

# Add middlewares
app.add_middleware(RateLimitMiddleware, requests_per_minute=60)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(
    conversations.router, prefix="/api/conversations", tags=["Conversations"]
)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "environment": ENVIRONMENT}


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint."""
    return {
        "message": "TenaChat API",
        "version": "1.0.0",
        "docs": "/docs" if ENVIRONMENT == "development" else "disabled",
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
