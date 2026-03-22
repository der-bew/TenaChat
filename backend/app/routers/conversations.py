"""
Conversation management endpoints for persistent chat history
version: 2.1.0
author: Derbew Felasman
"""

import logging
import uuid
from typing import Any, Optional

from app.db.supabase_client import supabase
from app.routers.auth import get_current_user
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateConversationRequest(BaseModel):
    title: Optional[str] = Field(
        default=None,
        description="Optional conversation title. If omitted, a default title is used.",
    )


class UpdateConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class MergeAnonymousHistoryRequest(BaseModel):
    anonymous_id: str = Field(..., min_length=1, max_length=255)
    title_prefix: str = Field(
        default="Imported Chat",
        min_length=1,
        max_length=100,
        description="Prefix used when creating imported conversations.",
    )


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    message_count: int = 0


class MessageItem(BaseModel):
    id: Optional[str] = None
    role: str
    content: str
    timestamp: Optional[str] = None


class ConversationDetail(BaseModel):
    id: str
    title: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    messages: list[MessageItem]


class CreateConversationResponse(BaseModel):
    conversation_id: str
    title: str


class MergeAnonymousHistoryResponse(BaseModel):
    imported_conversations: int
    imported_messages: int


def _safe_get(data: dict[str, Any], key: str, default: Any = None) -> Any:
    value = data.get(key, default)
    return default if value is None else value


def _ensure_conversation_owner(conversation_id: str, user_id: str) -> dict[str, Any]:
    result = (
        supabase.table("conversations")
        .select("*")
        .eq("id", conversation_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return result.data[0]


def _coerce_message_rows(rows: list[dict[str, Any]]) -> list[MessageItem]:
    return [
        MessageItem(
            id=item.get("id"),
            role=_safe_get(item, "role", "assistant"),
            content=_safe_get(item, "content", ""),
            timestamp=item.get("timestamp"),
        )
        for item in rows
    ]


def _fetch_anonymous_messages(anonymous_id: str) -> list[dict[str, Any]]:
    """
    Best-effort fetch of anonymous history from the same messages table.

    Expected schema support:
    - conversation_id
    - role
    - content
    - timestamp
    - optional anonymous_id OR user_id columns

    If the underlying schema does not support anonymous history persistence in
    Postgres, this returns an empty list and the merge endpoint becomes a no-op.
    """
    try:
        for column in ("anonymous_id", "user_id"):
            try:
                result = (
                    supabase.table("messages")
                    .select("conversation_id, role, content, timestamp")
                    .eq(column, anonymous_id)
                    .order("timestamp")
                    .execute()
                )
                if result.data:
                    return result.data
            except Exception:
                continue
    except Exception as e:
        logger.error("Failed to fetch anonymous history: %s", e, exc_info=True)

    return []


def _group_messages_by_conversation(
    rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        conversation_id = _safe_get(row, "conversation_id", "anonymous")
        grouped.setdefault(conversation_id, []).append(row)
    return grouped


@router.post(
    "/conversations",
    response_model=CreateConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    request: CreateConversationRequest,
    user_id: str = Depends(get_current_user),
) -> CreateConversationResponse:
    convo_id = str(uuid.uuid4())
    title = request.title.strip() if request.title else "New Conversation"

    data = {
        "id": convo_id,
        "user_id": user_id,
        "title": title,
    }

    try:
        result = supabase.table("conversations").insert(data).execute()
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create conversation",
            )

        return CreateConversationResponse(conversation_id=convo_id, title=title)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create conversation: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create conversation",
        ) from e


@router.get(
    "/conversations",
    response_model=list[ConversationSummary],
    status_code=status.HTTP_200_OK,
)
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user_id: str = Depends(get_current_user),
) -> list[ConversationSummary]:
    try:
        conversations_result = (
            supabase.table("conversations")
            .select("id, title, created_at, updated_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )

        conversations = conversations_result.data or []
        if not conversations:
            return []

        conversation_ids = [item["id"] for item in conversations]

        counts_result = (
            supabase.table("messages")
            .select("conversation_id")
            .in_("conversation_id", conversation_ids)
            .execute()
        )

        message_counts: dict[str, int] = {}
        for row in counts_result.data or []:
            convo_id = row.get("conversation_id")
            if convo_id:
                message_counts[convo_id] = message_counts.get(convo_id, 0) + 1

        return [
            ConversationSummary(
                id=item["id"],
                title=_safe_get(item, "title", "New Conversation"),
                created_at=item.get("created_at"),
                updated_at=item.get("updated_at"),
                message_count=message_counts.get(item["id"], 0),
            )
            for item in conversations
        ]
    except Exception as e:
        logger.error("Failed to list conversations: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list conversations",
        ) from e


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
    status_code=status.HTTP_200_OK,
)
async def get_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user),
) -> ConversationDetail:
    try:
        conversation = _ensure_conversation_owner(conversation_id, user_id)

        messages_result = (
            supabase.table("messages")
            .select("id, role, content, timestamp")
            .eq("conversation_id", conversation_id)
            .order("timestamp")
            .execute()
        )

        messages = _coerce_message_rows(messages_result.data or [])

        return ConversationDetail(
            id=conversation["id"],
            title=_safe_get(conversation, "title", "New Conversation"),
            created_at=conversation.get("created_at"),
            updated_at=conversation.get("updated_at"),
            messages=messages,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to fetch conversation %s: %s", conversation_id, e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch conversation",
        ) from e


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageItem],
    status_code=status.HTTP_200_OK,
)
async def list_conversation_messages(
    conversation_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user_id: str = Depends(get_current_user),
) -> list[MessageItem]:
    try:
        _ensure_conversation_owner(conversation_id, user_id)

        result = (
            supabase.table("messages")
            .select("id, role, content, timestamp")
            .eq("conversation_id", conversation_id)
            .order("timestamp")
            .range(offset, offset + limit - 1)
            .execute()
        )

        return _coerce_message_rows(result.data or [])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to list messages for conversation %s: %s",
            conversation_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list messages",
        ) from e


@router.patch(
    "/conversations/{conversation_id}",
    response_model=CreateConversationResponse,
    status_code=status.HTTP_200_OK,
)
async def update_conversation_title(
    conversation_id: str,
    request: UpdateConversationRequest,
    user_id: str = Depends(get_current_user),
) -> CreateConversationResponse:
    try:
        _ensure_conversation_owner(conversation_id, user_id)

        title = request.title.strip()
        result = (
            supabase.table("conversations")
            .update({"title": title})
            .eq("id", conversation_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update conversation",
            )

        return CreateConversationResponse(conversation_id=conversation_id, title=title)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to update conversation %s: %s",
            conversation_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update conversation",
        ) from e


@router.post(
    "/conversations/merge-anonymous",
    response_model=MergeAnonymousHistoryResponse,
    status_code=status.HTTP_200_OK,
)
async def merge_anonymous_history(
    request: MergeAnonymousHistoryRequest,
    user_id: str = Depends(get_current_user),
    x_anonymous_id: Optional[str] = Header(
        None, description="Optional anonymous session ID"
    ),
) -> MergeAnonymousHistoryResponse:
    anonymous_id = request.anonymous_id.strip() or (x_anonymous_id or "").strip()
    if not anonymous_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anonymous ID is required",
        )

    try:
        anonymous_rows = _fetch_anonymous_messages(anonymous_id)
        if not anonymous_rows:
            return MergeAnonymousHistoryResponse(
                imported_conversations=0,
                imported_messages=0,
            )

        grouped = _group_messages_by_conversation(anonymous_rows)
        imported_conversations = 0
        imported_messages = 0

        for _, rows in grouped.items():
            new_conversation_id = str(uuid.uuid4())
            first_user_message = next(
                (row.get("content", "") for row in rows if row.get("role") == "user"),
                "",
            )
            title_seed = first_user_message.strip() or request.title_prefix.strip()
            title = (
                f"{request.title_prefix.strip()}: {title_seed[:40]}"
                if first_user_message.strip()
                else request.title_prefix.strip()
            )

            conversation_insert = (
                supabase.table("conversations")
                .insert(
                    {
                        "id": new_conversation_id,
                        "user_id": user_id,
                        "title": title[:255] or "Imported Chat",
                    }
                )
                .execute()
            )

            if not conversation_insert.data:
                logger.warning(
                    "Skipping anonymous conversation import because conversation insert failed"
                )
                continue

            message_payload = [
                {
                    "conversation_id": new_conversation_id,
                    "role": _safe_get(row, "role", "assistant"),
                    "content": _safe_get(row, "content", ""),
                }
                for row in rows
                if _safe_get(row, "content", "")
            ]

            if message_payload:
                supabase.table("messages").insert(message_payload).execute()
                imported_messages += len(message_payload)

            imported_conversations += 1

        return MergeAnonymousHistoryResponse(
            imported_conversations=imported_conversations,
            imported_messages=imported_messages,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to merge anonymous history: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to merge anonymous history",
        ) from e


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, str]:
    try:
        _ensure_conversation_owner(conversation_id, user_id)

        supabase.table("messages").delete().eq(
            "conversation_id", conversation_id
        ).execute()
        supabase.table("conversations").delete().eq("id", conversation_id).eq(
            "user_id", user_id
        ).execute()

        return {"message": "Conversation deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to delete conversation %s: %s",
            conversation_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete conversation",
        ) from e
