"""
Chat endpoints for the app
version: 2.1.0
author: Derbew Felasman
"""

import base64
import logging
import tempfile
import uuid
from typing import Any, Optional, cast

from app.config import OPENAI_API_KEY
from app.db.supabase_client import supabase
from app.rag.graph import agent_graph
from app.routers.auth import get_current_user_or_anonymous
from app.utils.cache import (
    generate_cache_key,
    get_cached_response,
    save_anonymous_session,
    set_cached_response,
)
from app.utils.validation import sanitize_input, validate_uuid
from fastapi import APIRouter, Depends, Header, HTTPException, status
from langchain_core.messages import HumanMessage
from openai import OpenAI
from pydantic import BaseModel, Field, validator

logger = logging.getLogger(__name__)

router = APIRouter()


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


class ImageRequest(BaseModel):
    image_base64: str = Field(..., description="Base64 encoded image")
    message: Optional[str] = Field(None, description="Optional text prompt")
    language: str = Field("en", description="Response language")
    conversation_id: Optional[str] = Field(None, description="Optional conversation ID")

    @validator("conversation_id")
    def validate_image_conversation_id(cls, v: Optional[str]) -> Optional[str]:
        if v and not validate_uuid(v):
            raise ValueError("Invalid conversation ID format")
        return v


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    cached: bool = False
    tts_url: Optional[str] = None


class SpeechResponse(BaseModel):
    text: str
    detected_language: Optional[str] = None


class ImageResponse(BaseModel):
    response: str
    conversation_id: str


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


def _normalize_image_mime(payload: str) -> str:
    if payload.startswith("data:image/"):
        header = payload.split(",", 1)[0]
        mime = header.removeprefix("data:").split(";", 1)[0].strip().lower()
        allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        if mime in allowed:
            return mime
    return "image/jpeg"


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
    convo_id: str, user_id: str, is_anonymous: bool, title: str
) -> None:
    if is_anonymous:
        return

    result = (
        supabase.table("conversations")
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
    convo_id: str,
    user_id: str,
    is_anonymous: bool,
    user_message: str,
    assistant_message: str,
) -> None:
    if is_anonymous:
        return

    supabase.table("messages").insert(
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


def _build_tts_url(text: str, language: str = "en") -> str:
    return f"/api/chat/tts?text={text[:500]}&language={language}"


@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat_endpoint(
    request: ChatRequest,
    x_anonymous_id: Optional[str] = Header(None, description="Anonymous session ID"),
    user_id: Optional[str] = Depends(get_current_user_or_anonymous),
) -> ChatResponse:
    """
    Process a text chat message and return AI response.
    """
    try:
        resolved_user_id, is_anonymous = _get_or_create_user_id(user_id, x_anonymous_id)
        await _initialize_anonymous_session_if_needed(
            is_anonymous=is_anonymous,
            x_anonymous_id=x_anonymous_id,
            user_id=resolved_user_id,
        )

        convo_id = request.conversation_id or str(uuid.uuid4())
        logger.info(
            "Processing text chat for user %s, conversation %s, anonymous=%s",
            resolved_user_id,
            convo_id,
            is_anonymous,
        )

        if not request.conversation_id:
            try:
                _create_conversation_if_needed(
                    convo_id=convo_id,
                    user_id=resolved_user_id,
                    is_anonymous=is_anonymous,
                    title=request.message,
                )
            except HTTPException:
                raise
            except Exception as e:
                logger.error("Error creating conversation: %s", e, exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create conversation",
                ) from e

        cache_key = generate_cache_key(
            f"{resolved_user_id}:{convo_id}", request.message
        )
        cached_response = get_cached_response(cache_key)

        if cached_response:
            logger.info("Returning cached response for user %s", resolved_user_id)
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
            logger.info("Generated AI response for user %s", resolved_user_id)
        except Exception as e:
            logger.error("Error generating AI response: %s", e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate response. Please try again.",
            ) from e

        set_cached_response(cache_key, response)

        try:
            if is_anonymous:
                await save_anonymous_session(
                    resolved_user_id, convo_id, request.message, response
                )
            else:
                _save_chat_messages(
                    convo_id=convo_id,
                    user_id=resolved_user_id,
                    is_anonymous=is_anonymous,
                    user_message=request.message,
                    assistant_message=response,
                )
        except Exception as e:
            logger.error("Error saving messages: %s", e, exc_info=True)

        return ChatResponse(
            response=response,
            conversation_id=convo_id,
            cached=False,
            tts_url=_build_tts_url(response, request.language) if request.tts else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error in chat endpoint: %s", e, exc_info=True)
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
                    "model": "whisper-1",
                    "file": audio_file,
                }
                if request.language_hint:
                    transcription_kwargs["language"] = request.language_hint

                transcript = client.audio.transcriptions.create(**transcription_kwargs)

        text = (transcript.text or "").strip()

        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No speech detected in audio",
            )

        return SpeechResponse(
            text=text,
            detected_language=request.language_hint or None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in speech-to-text: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process audio",
        ) from e


@router.post("/image", response_model=ImageResponse)
async def analyze_image(
    request: ImageRequest,
    x_anonymous_id: Optional[str] = Header(None, description="Anonymous session ID"),
    user_id: Optional[str] = Depends(get_current_user_or_anonymous),
) -> ImageResponse:
    """
    Analyze an image using an OpenAI multimodal model with a health-focused prompt.
    """
    try:
        resolved_user_id, is_anonymous = _get_or_create_user_id(user_id, x_anonymous_id)
        await _initialize_anonymous_session_if_needed(
            is_anonymous=is_anonymous,
            x_anonymous_id=x_anonymous_id,
            user_id=resolved_user_id,
        )

        convo_id = request.conversation_id or str(uuid.uuid4())
        prompt = (
            request.message
            or "Analyze this image in the context of women's health. "
            "Describe only visible findings, avoid overclaiming, and advise the user "
            "to seek professional care for diagnosis."
        )

        if not request.conversation_id:
            try:
                _create_conversation_if_needed(
                    convo_id=convo_id,
                    user_id=resolved_user_id,
                    is_anonymous=is_anonymous,
                    title=prompt,
                )
            except HTTPException:
                raise
            except Exception as e:
                logger.error("Error creating image conversation: %s", e, exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create conversation",
                ) from e

        client = _require_openai_client()
        image_data = _decode_base64_payload(request.image_base64)
        image_b64 = base64.b64encode(image_data).decode("utf-8")
        image_mime = _normalize_image_mime(request.image_base64)

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful, safety-conscious women's health assistant. "
                        "Respond in Markdown. If the image is medical or health-related, "
                        "describe what is visible, mention uncertainty where appropriate, "
                        "and recommend professional medical evaluation when needed. "
                        "If the image is unrelated to health, respond briefly and say you can "
                        "help with health-related image questions. "
                        "Always respond in the user's requested language when possible. "
                        "For Amharic, Afaan Oromo, and Tigrinya, use natural phrasing and clear formatting."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Requested response language: {request.language}\n\n"
                                f"User prompt: {prompt}"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{image_mime};base64,{image_b64}",
                            },
                        },
                    ],
                },
            ],
        )

        response = (
            completion.choices[0].message.content.strip()
            if completion.choices and completion.choices[0].message.content
            else "I could not analyze that image."
        )

        try:
            if is_anonymous:
                await save_anonymous_session(
                    resolved_user_id, convo_id, f"[image] {prompt}", response
                )
            else:
                _save_chat_messages(
                    convo_id=convo_id,
                    user_id=resolved_user_id,
                    is_anonymous=is_anonymous,
                    user_message=f"[image] {prompt}",
                    assistant_message=response,
                )
        except Exception as e:
            logger.error("Error saving image analysis messages: %s", e, exc_info=True)

        return ImageResponse(response=response, conversation_id=convo_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error analyzing image: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process image",
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
