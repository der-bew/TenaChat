# TenaChat Architecture

This document describes the canonical architecture for TenaChat — a healthcare-oriented AI assistant for Ethiopian women's health.

---

## What was cleaned up

| Removed / Archived | Why |
|--------------------|-----|
| `src/ingestion/ingest.py` | Legacy pipeline using Google Vertex AI embeddings + Docling. Replaced by the canonical `backend/app/rag/indexer.py` which uses OpenAI embeddings + pymupdf4llm. |
| `docling`, `langchain-google-vertexai`, `langchain-google-genai`, `sentence-transformers`, `marker-pdf`, `google-generativeai`, `alembic`, `radis` deps | Only used by the legacy ingestion path or were experimental. Removed to reduce build surface and attack surface. |

---

## Canonical component map

```
Browser (Next.js 14)
  │
  │  HTTPS / WebSocket
  ▼
FastAPI backend  (Python 3.12)
  ├── RateLimitMiddleware (Redis-backed)
  ├── CORSMiddleware
  ├── /auth/*       — convenience auth for non-JS clients
  ├── /api/chat/*   — chat, speech-to-text, image analysis, TTS
  └── /api/conversations/*  — conversation history CRUD

  Chat flow
  ─────────
  ChatRequest
    → triage.classify_triage()  [EMERGENCY → escalation response, stop]
    → health domain check        [non-health → refusal, stop]
    → retrieval (_retrieve_with_sources)  [FAISS local vector DB]
    → grounding check            [no evidence → uncertainty fallback, stop]
    → LLM generate (OpenRouter gemma-4-31b-it:free → fallback gemini-2.5-flash) [evidence-grounded response]
    → ChatResponse (response + sources + triage_level)

  Storage / cache
  ───────────────
  Redis         — response cache + anonymous sessions + rate limiting
  Supabase      — conversation history (messages table), user auth (JWT)
  FAISS (local) — vector index for knowledge base

  Indexing (offline / separate from serving)
  ──────────────────────────────────────────
  backend/app/rag/indexer.py
    reads knowledge_base/data/*.pdf   via pymupdf4llm
    reads knowledge_base/*.json       raw JSON
    chunks with RecursiveCharacterTextSplitter (1500 / 200)
    embeds with text-embedding-3-large (OpenAI)
    saves to knowledge_base/index.faiss + index.pkl
```

---

## Frontend flow

1. User opens the app — Supabase JS SDK is used for auth (sign-up / login / session refresh).
2. Authenticated sessions send `Authorization: Bearer <supabase_jwt>` on all API calls.
3. Anonymous sessions use a random `X-Anonymous-Id` header instead.
4. The chat page (`src/app/page.tsx`) calls `POST /api/chat/chat`.
5. The response includes `response`, `conversation_id`, `sources[]`, and `triage_level`.
6. `ChatMessage` renders Markdown content and displays source citations beneath assistant messages.

---

## Backend flow

```
POST /api/chat/chat
  1. Validate ChatRequest (message, language, conversation_id)
  2. Resolve user (authenticated or anonymous)
  3. Check Redis cache → return cached response if hit
  4. Build LangGraph AgentState
  5. agent_graph.invoke(state)
     a. retrieve()  — triage → health check → FAISS retrieval → metrics log
     b. generate()  — emergency / non-health / insufficient-evidence / LLM
  6. Cache the response
  7. Persist messages to Supabase (authenticated users only)
  8. Return ChatResponse
```

---

## Auth flow

**Canonical: Frontend-first Supabase Auth**

| Client type | How to authenticate |
|-------------|---------------------|
| Browser (Next.js) | Use `@supabase/supabase-js` + `@supabase/auth-helpers-nextjs`. Supabase handles session refresh. Pass the JWT as `Authorization: Bearer <token>`. |
| Non-browser / API | Use `POST /auth/signup` and `POST /auth/login` to obtain a token, then send `Authorization: Bearer <token>`. |

Backend authorization is handled by two FastAPI dependencies in `app/routers/auth.py`:

- `get_current_user` — requires a valid bearer token.
- `get_current_user_or_anonymous` — returns user ID or `None` (anonymous).

---

## Retrieval / indexing flow

**Offline indexing** (run once, or when knowledge base changes):

```bash
uv run python backend/app/rag/indexer.py
```

This produces `knowledge_base/index.faiss` and `knowledge_base/index.pkl`.

**Runtime retrieval** (per chat request):

1. `_load_vectorstore()` loads the FAISS index lazily on first request.
2. `_retrieve_with_sources(query)` calls `similarity_search(k=5)`.
3. Returns `(context_text, sources)` — sources are deduplicated metadata dicts.
4. Retrieval latency and source count are logged for observability.

---

## Safety layer

Every request passes through `app/rag/triage.py` before the LLM is invoked:

| Triage level | Trigger | Response |
|--------------|---------|----------|
| `EMERGENCY` | Red-flag keywords (heavy bleeding, unconscious, suicidal, etc.) | Safe escalation message directing user to emergency services. No LLM call. |
| `ROUTINE` (no evidence) | FAISS returns no useful documents | Transparent uncertainty fallback. No speculative LLM response. |
| `ROUTINE` (with evidence) | Normal health query with retrieved context | LLM generates an evidence-grounded response. |

The triage layer is **deterministic and keyword-based** — no ML required, auditable, and predictable.

---

## Storage / cache components

| Component | Purpose | Notes |
|-----------|---------|-------|
| Redis | Response cache, anonymous session storage, rate limiting | Optional; app degrades gracefully if unavailable |
| Supabase (PostgreSQL) | Conversation history, user accounts | Required for authenticated flows |
| FAISS (local disk) | Vector index for knowledge base retrieval | See pgvector migration path below |

---

## Request lifecycle (summary)

```
Client → CORS + Rate limit → Auth resolve → Cache check
       → (cache miss) LangGraph retrieve → triage → retrieval → generate
       → Cache set → Persist to Supabase → Response with sources
```

---

## What is canonical and what was removed

### Canonical

- `backend/app/rag/indexer.py` — single indexing pipeline (OpenAI + pymupdf4llm + FAISS)
- `backend/app/rag/graph.py` — LangGraph agent (retrieve → generate)
- `backend/app/rag/triage.py` — medical safety triage layer
- Frontend Supabase Auth — canonical authentication path

### Removed

- `src/ingestion/ingest.py` — legacy Vertex AI + Docling pipeline (not canonical)
- Google AI / Vertex AI / Sentence-Transformers / Docling / marker-pdf dependencies

---

## Future: pgvector migration

See [`docs/pgvector_migration.md`](pgvector_migration.md) for a lightweight migration path from FAISS to Supabase pgvector when usage grows.

## Future: Ingestion scaling

See [`docs/ingestion_scaling.md`](ingestion_scaling.md) for a path toward async / queued ingestion jobs.

## Observability

See [`docs/observability.md`](observability.md) for logging conventions, correlation IDs, and monitoring guidance.
