# TenaChat

An AI-powered health chatbot focused on Ethiopian women’s health, built with a FastAPI backend, a Next.js frontend, retrieval-augmented generation (RAG), OpenAI models, Redis caching, and Supabase-backed conversation history.

This project is designed to answer **health-related questions only**. The assistant uses a local FAISS knowledge index built from PDF and JSON health resources, short-term chat memory, long-term conversation history, and optional web search for current health topics.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Core Capabilities](#core-capabilities)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Environment Variables](#environment-variables)
- [Local Development](#local-development)
- [Knowledge Base Indexing](#knowledge-base-indexing)
- [Production Docker Setup](#production-docker-setup)
- [Docker Compose Deployment Workflow](#docker-compose-deployment-workflow)
- [Operational Notes](#operational-notes)
- [Security Notes](#security-notes)
- [Known Limitations](#known-limitations)

---

## Overview

The chatbot provides a health-focused conversational experience with:

- a **FastAPI** backend for chat, retrieval, and health APIs
- a **Next.js** frontend for the web experience
- **OpenAI `gpt-4o-mini`** for chat responses
- **OpenAI `text-embedding-3-large`** for semantic retrieval
- **FAISS** for local vector search
- **Supabase** for persisted conversation history
- **Redis** for caching and anonymous session support
- **Serper** for optional web search on time-sensitive health questions

The assistant is constrained to **health-domain questions** and should refuse unrelated prompts.

---

## Architecture

### Request Flow

1. The frontend sends a user message to the backend.
2. The backend creates or loads the conversation state.
3. The agent applies a **health-only guardrail**.
4. For health-related prompts, the backend gathers:
   - short-term memory from the active thread
   - long-term memory from Supabase conversation history
   - retrieved health context from FAISS
   - optional web search context from Serper for current topics
5. The backend sends the aggregated context to **OpenAI `gpt-4o-mini`**.
6. The response is returned to the client and optionally cached/stored.

### RAG Flow

1. Source documents are collected from `knowledge_base/`
2. PDFs are extracted using `pymupdf4llm`
3. JSON documents are serialized into stable text
4. Content is chunked with `RecursiveCharacterTextSplitter`
5. Chunks are embedded with `text-embedding-3-large`
6. Embeddings are stored in a local **FAISS** index inside `knowledge_base/`

---

## Core Capabilities

- Health-only conversational assistant
- Retrieval-augmented responses from local knowledge files
- Short-term and long-term memory
- Optional current-information lookup via Serper
- Anonymous and authenticated conversation flows
- Redis-backed caching
- Speech and image route scaffolding

---

## Tech Stack

### Backend

- FastAPI
- LangGraph
- LangChain
- OpenAI
- FAISS
- Supabase
- Redis
- PyMuPDF / `pymupdf4llm`
- Loguru

### Frontend

- Next.js 14
- React 18
- TypeScript
- Tailwind CSS
- shadcn/ui
- Supabase JS

### Tooling

- `uv` for Python dependency management
- `npm` for frontend package management
- Docker
- Docker Compose

---

## Project Structure

```text
tenachat/
├── backend/
│   ├── app/
│   │   ├── db/                  # Supabase client and DB-related code
│   │   ├── middleware/          # Middleware such as rate limiting
│   │   ├── rag/                 # Agent graph, retrieval, indexer
│   │   ├── routers/             # FastAPI route modules
│   │   └── utils/               # Cache, validation, helpers
│   ├── Dockerfile
│   └── main.py                  # FastAPI application entrypoint
├── frontend/
│   ├── src/
│   │   ├── app/                 # Next.js app routes
│   │   ├── components/          # UI components
│   │   └── lib/                 # Shared frontend utilities
│   ├── Dockerfile
│   ├── next.config.js
│   ├── package.json
│   └── package-lock.json
├── knowledge_base/              # PDF / JSON sources and FAISS index files
├── .dockerignore
├── docker-compose.yml
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## Environment Variables

Create a root `.env` file for backend/runtime services.

### Required Backend Variables

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_service_or_access_key
OPENAI_API_KEY=your_openai_api_key
```

### Optional / Recommended Backend Variables

```env
SERPER_API_KEY=your_serper_api_key
REDIS_URL=redis://redis:6379/0
ENVIRONMENT=production
CORS_ORIGINS=http://localhost:3000
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
INDEX_BATCH_SIZE=12
INDEX_MAX_PDFS=0
INDEX_MAX_JSON_FILES=0
LOG_LEVEL=INFO
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Notes

- `OPENAI_API_KEY` is required for:
  - chat generation
  - embedding generation
  - current multimodal route implementation
- `SERPER_API_KEY` is required only if web search should be enabled
- `REDIS_URL` is set automatically for Docker Compose, but keeping it in `.env` is fine
- frontend public variables are injected through Docker Compose for the frontend service

---

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 20+
- `uv`
- npm
- Redis
- Supabase project
- OpenAI API key
- Serper API key if web search is desired

### Backend

```bash
uv sync
uv run python backend/main.py
```

Backend runs on:

- `http://localhost:8000`

### Frontend

```bash
cd frontend
npm ci
npm run dev
```

Frontend runs on:

- `http://localhost:3000`

---

## Knowledge Base Indexing

Build or rebuild the FAISS index with:

```bash
uv run python backend/app/rag/indexer.py
```

### Indexer behavior

- recursively scans `knowledge_base/` for:
  - `*.pdf`
  - `*.json`
- extracts PDFs using `pymupdf4llm`
- converts JSON to stable text
- chunks content
- embeds chunks with OpenAI
- saves the FAISS index back into `knowledge_base/`

### Important

Before running the indexer:

- ensure `OPENAI_API_KEY` is set
- ensure your root `.env` exists or the variables are exported in the shell

---

## Production Docker Setup

The repository includes a production-oriented container setup for:

- backend
- frontend
- redis

### Backend image characteristics

The backend Dockerfile is designed for production with:

- multi-stage build
- Python 3.12 slim base
- dependency installation via `uv` and `uv.lock`
- non-root runtime user
- minimal runtime packages
- baked-in application code and `knowledge_base`
- container healthcheck against `/health`

### Frontend image characteristics

The frontend Dockerfile is designed for production with:

- multi-stage build
- Node 20 Alpine
- `npm ci`
- production build during image creation
- non-root runtime user
- runtime healthcheck
- production `next start`

### Redis service characteristics

The Compose stack runs Redis with:

- append-only persistence enabled
- healthcheck using `redis-cli ping`
- isolated service networking
- managed named volume

---

## Docker Compose Deployment Workflow

The provided `docker-compose.yml` is intended for a production-like deployment workflow.

### What it provides

- service restart policies
- Redis healthcheck
- backend healthcheck
- frontend healthcheck
- backend startup ordered after Redis is healthy
- frontend startup ordered after backend is healthy
- no source bind mounts
- isolated bridge network
- named Redis volume
- backend and frontend built from the repository root

### Step 1: create `.env`

At the project root, create `.env` with the required backend/runtime values:

```env
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_service_or_access_key
OPENAI_API_KEY=your_openai_api_key
SERPER_API_KEY=your_serper_api_key
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
NEXT_PUBLIC_API_URL=http://localhost:8000
CORS_ORIGINS=http://localhost:3000
ENVIRONMENT=production
```

### Step 2: optionally rebuild the FAISS index

If your knowledge base has changed:

```bash
uv run python backend/app/rag/indexer.py
```

### Step 3: build and start the stack

```bash
docker compose up --build -d
```

### Step 4: verify service health

```bash
docker compose ps
```

You should verify:

- `backend` is healthy
- `frontend` is healthy
- `redis` is healthy

### Step 5: test endpoints

Backend health:

```bash
curl http://localhost:8000/health
```

Frontend:

Open:

- `http://localhost:3000`

### Step 6: inspect logs if needed

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f redis
```

### Step 7: stop the stack

```bash
docker compose down
```

To remove Redis persisted data as well:

```bash
docker compose down -v
```

---

## Operational Notes

### Backend runtime

The backend container starts with:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Frontend runtime

The frontend container starts with:

```bash
npm start
```

### Ports

Default exposed ports:

- frontend: `3000`
- backend: `8000`

Redis is kept internal to the Compose network in the current setup.

### Data persistence

Redis persistence is backed by the named Docker volume:

- `redis_data`

### Logging

All services log to stdout/stderr for container-native log aggregation.

### Healthchecks

Configured checks include:

- backend: `GET /health`
- frontend: basic HTTP reachability
- redis: `redis-cli ping`

---

## Security Notes

- The chatbot is guarded to answer **health-related questions only**
- Docs are disabled outside development mode in the FastAPI app
- Inputs are sanitized in the chat flow
- Redis-backed anonymous sessions use TTL behavior
- Services run without development bind mounts in the production compose setup
- Containers use non-root runtime users for backend and frontend

### Still recommended for real production environments

- run behind a reverse proxy with TLS
- restrict `CORS_ORIGINS` to your real frontend origin
- manage secrets with a proper secret manager
- scan images in CI/CD
- audit dependencies regularly
- add monitoring and centralized logging
- implement backup/restore procedures for persistent services

---

## Known Limitations

- Health guardrails are currently keyword-based, not classifier-model based
- FAISS is local-disk based and may not be ideal for large multi-instance scaling
- PDF extraction quality depends on source quality
- OCR is limited when Tesseract language data is unavailable
- multimodal routes should be validated continuously against the exact OpenAI message format used in production

---

## Deployment Recommendations

For a more mature production deployment, consider:

1. separating development and production Compose files
2. adding a reverse proxy such as Nginx or Traefik
3. externalizing persistent storage and secrets
4. treating indexing as a separate operational job rather than part of app startup
5. moving beyond local FAISS if horizontal scale becomes important

---

## License

MIT

## Author

Derbew Felasman