# pgvector Migration Guide

This document describes how to migrate TenaChat from local FAISS to Supabase pgvector when usage grows.

---

## When to migrate

Consider migrating from FAISS to pgvector when:

- You need **multi-instance deployment** (FAISS index is local disk, not shared across replicas).
- The knowledge base grows large enough that rebuilding FAISS is operationally painful.
- You want **incremental indexing** without full rebuilds.
- You need **tenant isolation** or **per-user knowledge scoping**.
- You are already using Supabase and want to consolidate infrastructure.

For a single-instance deployment with a stable knowledge base, FAISS is fine.

---

## Architecture target

```
Current (FAISS):
  indexer.py → knowledge_base/index.faiss + index.pkl
  graph.py   → FAISS.load_local("knowledge_base", embeddings)

Target (pgvector):
  indexer.py → Supabase table: documents (id, content, embedding, metadata)
  graph.py   → SupabaseVectorStore.similarity_search(query, k=5)
```

---

## Migration steps

### 1. Enable pgvector in Supabase

In the Supabase SQL editor:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    content     text NOT NULL,
    embedding   vector(3072),  -- text-embedding-3-large produces 3072-dim vectors
    source      text,
    file_type   text,
    file_path   text,
    created_at  timestamptz DEFAULT now()
);

CREATE INDEX ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

### 2. Update the indexer

Replace the FAISS upsert logic in `backend/app/rag/indexer.py` with:

```python
from langchain_community.vectorstores import SupabaseVectorStore

vectorstore = SupabaseVectorStore.from_documents(
    documents=chunks,
    embedding=embeddings,
    client=supabase_client,
    table_name="documents",
    query_name="match_documents",
)
```

Add a Supabase RPC function for similarity search:

```sql
CREATE OR REPLACE FUNCTION match_documents(
    query_embedding vector(3072),
    match_count     int DEFAULT 5,
    filter          jsonb DEFAULT '{}'
)
RETURNS TABLE (id uuid, content text, metadata jsonb, similarity float)
LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.content,
        jsonb_build_object('source', d.source, 'file_type', d.file_type) AS metadata,
        1 - (d.embedding <=> query_embedding) AS similarity
    FROM documents d
    ORDER BY d.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
```

### 3. Update graph.py retrieval

Replace `_load_vectorstore()` / `FAISS.load_local(...)` with:

```python
from langchain_community.vectorstores import SupabaseVectorStore

def _load_vectorstore():
    return SupabaseVectorStore(
        client=supabase,
        embedding=_init_embeddings(),
        table_name="documents",
        query_name="match_documents",
    )
```

The `_retrieve_with_sources()` function stays identical — it just calls
`vs.similarity_search(query, k=5)` which works on any LangChain VectorStore.

### 4. Environment variable

Add to your `.env`:

```env
# pgvector: set to "pgvector" to switch from FAISS
VECTOR_BACKEND=pgvector
```

Update `_load_vectorstore()` to branch on `VECTOR_BACKEND`.

---

## Abstraction interface

The current code already uses LangChain's `VectorStore` interface.  Both
`FAISS` and `SupabaseVectorStore` implement `similarity_search()`, so switching
the backend requires changing only the initialization code in `graph.py` and
`indexer.py`.

The `_retrieve_with_sources()` helper is intentionally backend-agnostic.

---

## Rollback plan

- Keep the FAISS index files in place until pgvector migration is validated.
- Feature-flag the backend with `VECTOR_BACKEND=faiss` (default) vs `VECTOR_BACKEND=pgvector`.
- Run both in parallel for a validation period before cutting over.

---

## References

- [Supabase pgvector guide](https://supabase.com/docs/guides/ai/vector-columns)
- [LangChain SupabaseVectorStore](https://python.langchain.com/docs/integrations/vectorstores/supabase)
