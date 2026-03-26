# Ingestion Scaling Guide

This document describes the current indexing approach and a practical path toward asynchronous, queued ingestion as the knowledge base or ingestion frequency grows.

---

## Current approach

Indexing is **manual and offline**:

```bash
uv run python backend/app/rag/indexer.py
```

This script:
1. Scans `knowledge_base/data/` for `*.pdf` and `*.json` files.
2. Extracts text with `pymupdf4llm`.
3. Chunks with `RecursiveCharacterTextSplitter`.
4. Embeds with OpenAI `text-embedding-3-large`.
5. Saves a local FAISS index to `knowledge_base/`.

**This path is clearly separated from runtime serving.** The FastAPI backend loads
the FAISS index lazily at startup and never writes to it.

---

## When to scale ingestion

Consider moving to queued/async ingestion when:

- Documents are added frequently and the manual rebuild is operationally burdensome.
- Document processing takes too long to do synchronously (large PDFs, many files).
- You need to support user-uploaded documents that must be indexed on demand.
- You have moved to pgvector and want incremental upserts instead of full rebuilds.

---

## Practical scaling path

### Step 1: Wrap the indexer as a callable job

The `build_index()` function in `backend/app/rag/indexer.py` is already
self-contained and accepts configuration via environment variables.  Wrap it
as a Celery task or background job:

```python
# backend/app/tasks/index_documents.py
from celery import Celery
from app.rag.indexer import build_index

celery_app = Celery("tenachat", broker="redis://localhost:6379/1")

@celery_app.task(name="index_documents")
def index_documents_task():
    build_index()
```

### Step 2: Trigger indexing via an admin endpoint or file watcher

**Option A — Admin HTTP endpoint:**

```python
@router.post("/admin/reindex", dependencies=[Depends(require_admin)])
async def trigger_reindex():
    index_documents_task.delay()
    return {"status": "indexing queued"}
```

**Option B — File system watcher (for local dev):**

Use `watchdog` to detect new files in `knowledge_base/data/` and trigger
`index_documents_task.delay()`.

**Option C — Scheduled job:**

Use Celery beat or a cron job to rebuild the index nightly:

```
0 2 * * * uv run python backend/app/rag/indexer.py
```

### Step 3: Track indexing jobs

Add a simple jobs table or log to track when indexing ran, how many documents
were processed, and whether it succeeded:

```sql
CREATE TABLE indexing_jobs (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at  timestamptz DEFAULT now(),
    finished_at timestamptz,
    status      text,  -- 'running', 'success', 'failed'
    docs_indexed int,
    error       text
);
```

---

## Document boundary: indexing vs serving

```
Indexing (offline)                    Serving (runtime)
─────────────────────────────────    ─────────────────────────────────
backend/app/rag/indexer.py           backend/app/rag/graph.py
  reads: knowledge_base/data/          reads: knowledge_base/index.faiss
  writes: knowledge_base/index.faiss   (never writes)
```

**Rule:** The serving path (FastAPI + LangGraph) is **read-only** with respect to
the vector index.  All writes to the index go through the indexer.

This boundary makes it safe to scale the serving layer horizontally without
worrying about write conflicts on the index.

---

## Redis as a simple queue

TenaChat already depends on Redis.  For simple async jobs you can use Redis
directly via `rq` (Redis Queue) without adding Celery:

```bash
pip install rq
```

```python
from redis import Redis
from rq import Queue
from app.rag.indexer import build_index

q = Queue(connection=Redis.from_url(REDIS_URL))
q.enqueue(build_index)
```

Start a worker:

```bash
rq worker --with-scheduler
```

This is lightweight and leverages the existing Redis dependency.

---

## Concurrency and locking

If multiple workers could trigger indexing simultaneously, add a distributed
lock before writing the index:

```python
import redis

r = redis.from_url(REDIS_URL)
lock = r.lock("indexing_lock", timeout=600)

if lock.acquire(blocking=False):
    try:
        build_index()
    finally:
        lock.release()
else:
    logger.info("Indexing already in progress, skipping.")
```
