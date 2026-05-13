"""
Chat endpoints for the app
version: 3.0.0
author: Derbew Felasman
"""

import base64
import logging
import os
import tempfile
import uuid
from typing import Any, List, Optional, cast

from app.config import OPENAI_API_KEY
from app.db.supabase_client import get_supabase_client, supabase
from app.rag.graph import agent_graph
from app.routers.auth import get_current_user_or_anonymous, oauth2_scheme
from app.utils.cache import (
    generate_cache_key,
    get_cached_response,
    save_anonymous_session,
    set_cached_response,
)
from app.utils.validation import sanitize_input, validate_uuid
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from langchain_core.messages import HumanMessage
from openai import OpenAI
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)

router = APIRouter()
OPENAI_TRANSCRIPTION_MODEL = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-transcribe")

TRANSCRIPTION_LANGUAGE_HINTS = {
    "en": "en",
    "am": None,
    "om": None,
    "ti": None,
}


def _normalize_transcription_language_hint(language_hint: Optional[str]) -> Optional[str]:
    if not language_hint:
        return None

    normalized = language_hint.strip().lower()
    return TRANSCRIPTION_LANGUAGE_HINTS.get(normalized, normalized)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="User message")
    conversation_id: Optional[str] = Field(None, description="Optional conversation ID")
    tts: bool = Field(False, description="Whether to return text-to-speech URL")
    language: str = Field("en", description="Preferred response language")

    @validator("message")
    def validate_message(cls, v: str) -> str:
        """Validate and sanitize message."""
        try:
            return sanitize_input(v)
        except ValueError as e:
            raise ValueError(f"Invalid message: {str(e)}") from e

    @validator("conversation_id")
    def validate_conversation_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate conversation ID format."""
        if v and not validate_uuid(v):
            raise ValueError("Invalid conversation ID format")
        return v


class SpeechRequest(BaseModel):
    audio_base64: str = Field(..., description="Base64 encoded audio file")
    format: str = Field(
        "webm", description="Audio format: webm, mp3, wav, m4a, mp4, mpeg"
    )
    language_hint: Optional[str] = Field(
        None, description="Optional ISO language hint for better accuracy"
    )


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    cached: bool = False
    tts_url: Optional[str] = None
    # Source documents used to ground the response (empty when cached or not applicable)
    sources: List[dict] = Field(default_factory=list)
    # Triage level: "routine" or "emergency"
    triage_level: Optional[str] = None


class SpeechResponse(BaseModel):
    text: str
    detected_language: Optional[str] = None


def _require_openai_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OPENAI_API_KEY is not configured",
        )
    return OpenAI(api_key=OPENAI_API_KEY)


def _decode_base64_payload(payload: str) -> bytes:
    """Decode raw base64 or data-URL base64 payload safely."""
    try:
        raw_payload = payload.split(",", 1)[1] if "," in payload else payload
        return base64.b64decode(raw_payload)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid base64 payload",
        ) from e


def _normalize_audio_suffix(audio_format: str) -> str:
    normalized = (audio_format or "webm").lower().strip()
    allowed = {"webm", "mp3", "wav", "m4a", "mp4", "mpeg"}
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format: {audio_format}",
        )
    return f".{normalized}"


def _get_or_create_user_id(
    user_id: Optional[str], x_anonymous_id: Optional[str]
) -> tuple[str, bool]:
    is_anonymous = user_id is None
    if is_anonymous:
        resolved_user_id = x_anonymous_id or str(uuid.uuid4())
        return resolved_user_id, True
    return user_id, False


async def _initialize_anonymous_session_if_needed(
    is_anonymous: bool,
    x_anonymous_id: Optional[str],
    user_id: str,
) -> None:
    if is_anonymous and not x_anonymous_id:
        await save_anonymous_session(user_id)


def _create_conversation_if_needed(
    db_client: Any, convo_id: str, user_id: str, is_anonymous: bool, title: str
) -> None:
    if is_anonymous:
        return

    result = (
        db_client.table("conversations")
        .insert(
            {
                "id": convo_id,
                "user_id": user_id,
                "title": title[:50] or "New Chat",
            }
        )
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create conversation",
        )


def _save_chat_messages(
    db_client: Any,
    convo_id: str,
    user_id: str,
    is_anonymous: bool,
    user_message: str,
    assistant_message: str,
) -> None:
    if is_anonymous:
        return

    db_client.table("messages").insert(
        [
            {
                "conversation_id": convo_id,
                "role": "user",
                "content": user_message,
            },
            {
                "conversation_id": convo_id,
                "role": "assistant",
                "content": assistant_message,
            },
        ]
    ).execute()


async def _persist_chat_messages_after_response(
    convo_id: str,
    user_id: str,
    is_anonymous: bool,
    token: Optional[str],
    user_message: str,
    assistant_message: str,
) -> None:
    try:
        if is_anonymous:
            await save_anonymous_session(
                user_id, convo_id, user_message, assistant_message
            )
            return

        db_client = get_supabase_client(token) if token else supabase
        _save_chat_messages(
            db_client=db_client,
            convo_id=convo_id,
            user_id=user_id,
            is_anonymous=False,
            user_message=user_message,
            assistant_message=assistant_message,
        )
    except Exception as e:
        logger.error("Error saving messages after response: %s", e, exc_info=True)


def _build_tts_url(text: str, language: str = "en") -> str:
    return f"/api/chat/tts?text={text[:500]}&language={language}"


@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_endpoint(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    x_anonymous_id: Optional[str] = Header(None, description="Anonymous session ID"),
    x_request_id: Optional[str] = Header(None, description="Client-supplied correlation ID"),
    user_id: Optional[str] = Depends(get_current_user_or_anonymous),
    token: Optional[str] = Depends(oauth2_scheme),
) -> ChatResponse:
    """
    Process a text chat message and return AI response.
    """
    # Correlation ID for tracing this request through logs
    correlation_id = x_request_id or str(uuid.uuid4())
    log = logging.LoggerAdapter(logger, {"correlation_id": correlation_id})

    try:
        resolved_user_id, is_anonymous = _get_or_create_user_id(user_id, x_anonymous_id)
        await _initialize_anonymous_session_if_needed(
            is_anonymous=is_anonymous,
            x_anonymous_id=x_anonymous_id,
            user_id=resolved_user_id,
        )

        convo_id = request.conversation_id or str(uuid.uuid4())
        db_client = get_supabase_client(token) if token else supabase
        log.info(
            "Processing text chat | user=%s | conversation=%s | anonymous=%s",
            resolved_user_id,
            convo_id,
            is_anonymous,
        )

        if not request.conversation_id:
            try:
                _create_conversation_if_needed(
                    db_client=db_client,
                    convo_id=convo_id,
                    user_id=resolved_user_id,
                    is_anonymous=is_anonymous,
                    title=request.message,
                )
            except HTTPException:
                raise
            except Exception as e:
                log.error("Error creating conversation: %s", e, exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create conversation",
                ) from e

        cache_key = generate_cache_key(
            f"{resolved_user_id}:{convo_id}", request.message
        )
        cached_response = get_cached_response(cache_key)

        if cached_response:
            log.info("Returning cached response | user=%s", resolved_user_id)
            return ChatResponse(
                response=cached_response,
                conversation_id=convo_id,
                cached=True,
                tts_url=_build_tts_url(cached_response, request.language)
                if request.tts
                else None,
            )

        try:
            state: dict[str, object] = {
                "messages": [HumanMessage(content=request.message)],
                "user_id": resolved_user_id,
                "conversation_id": convo_id,
                "language": request.language,
                "requested_language": request.language,
                "auth_token": token,
                "has_existing_conversation": bool(request.conversation_id),
                "is_anonymous": is_anonymous,
            }

            result = agent_graph.invoke(
                cast(Any, state),
                config={
                    "configurable": {"thread_id": f"{resolved_user_id}_{convo_id}"}
                },
            )

            final_message = result["messages"][-1]
            response = (
                final_message.content
                if hasattr(final_message, "content")
                and isinstance(final_message.content, str)
                else str(final_message)
            )
            raw_sources = result.get("sources")
            sources: List[dict] = raw_sources if isinstance(raw_sources, list) else []
            raw_triage = result.get("triage_level")
            triage_level: Optional[str] = raw_triage if isinstance(raw_triage, str) else None
            log.info(
                "Generated AI response | user=%s | triage=%s | sources=%d",
                resolved_user_id,
                triage_level,
                len(sources),
            )
        except Exception as e:
            log.error("Error generating AI response: %s", e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate response. Please try again.",
            ) from e

        set_cached_response(cache_key, response)

        background_tasks.add_task(
            _persist_chat_messages_after_response,
            convo_id,
            resolved_user_id,
            is_anonymous,
            token,
            request.message,
            response,
        )

        return ChatResponse(
            response=response,
            conversation_id=convo_id,
            cached=False,
            tts_url=_build_tts_url(response, request.language) if request.tts else None,
            sources=sources,
            triage_level=triage_level,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Unexpected error in chat endpoint | correlation_id=%s: %s",
            correlation_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        ) from e


@router.post("/speech", response_model=SpeechResponse)
async def speech_to_text(
    request: SpeechRequest,
    x_anonymous_id: Optional[str] = Header(None, description="Anonymous session ID"),
    user_id: Optional[str] = Depends(get_current_user_or_anonymous),
) -> SpeechResponse:
    """
    Convert speech to text using OpenAI Whisper.
    """
    try:
        resolved_user_id, is_anonymous = _get_or_create_user_id(user_id, x_anonymous_id)
        await _initialize_anonymous_session_if_needed(
            is_anonymous=is_anonymous,
            x_anonymous_id=x_anonymous_id,
            user_id=resolved_user_id,
        )

        audio_data = _decode_base64_payload(request.audio_base64)
        suffix = _normalize_audio_suffix(request.format)
        client = _require_openai_client()

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(audio_data)
            tmp.flush()

            with open(tmp.name, "rb") as audio_file:
                transcription_kwargs: dict[str, Any] = {
                    "model": OPENAI_TRANSCRIPTION_MODEL,
                    "file": audio_file,
                }
                normalized_language_hint = _normalize_transcription_language_hint(
                    request.language_hint
                )
                if normalized_language_hint:
                    transcription_kwargs["language"] = normalized_language_hint

                transcript = client.audio.transcriptions.create(**transcription_kwargs)

        text = (transcript.text or "").strip()

        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No speech detected in audio",
            )

        return SpeechResponse(
            text=text,
            detected_language=_normalize_transcription_language_hint(
                request.language_hint
            )
            or None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in speech-to-text: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process audio",
        ) from e


@router.get("/tts")
async def text_to_speech(text: str, language: str = "en"):
    """
    Generate speech audio using OpenAI text-to-speech.
    """
    from fastapi.responses import Response

    try:
        client = _require_openai_client()
        speech = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text[:2000],
        )

        audio_bytes = speech.read()
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating TTS audio: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate speech audio",
        ) from e
