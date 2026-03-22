"""
Build FAISS index for Ethiopian Women's Health Chatbot KB
Uses OpenAI multilingual embeddings for PDFs and JSON knowledge files
version: 5.0.0
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

import pymupdf4llm  # type: ignore[import-not-found]
from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings  # type: ignore[import-not-found]
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger
from pydantic import SecretStr

# Load environment variables from the project root explicitly
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
CHUNK_SIZE = 1500
CHUNK_OVERLAP = 200
DEFAULT_BATCH_SIZE = int(os.getenv("INDEX_BATCH_SIZE", "12"))
MAX_PDFS = int(os.getenv("INDEX_MAX_PDFS", "0"))
MAX_JSON_FILES = int(os.getenv("INDEX_MAX_JSON_FILES", "0"))


logger.remove()
logger.add(sys.stderr, level=os.getenv("LOG_LEVEL", "INFO"))


def _json_to_text(data: Any) -> str:
    """Convert JSON payload to a stable text representation for chunking/embedding."""
    return json.dumps(data, ensure_ascii=False, indent=2)


def _iter_files(base_dir: Path, patterns: tuple[str, ...]) -> list[Path]:
    """Recursively collect files matching the given patterns."""
    files: list[Path] = []
    for pattern in patterns:
        files.extend(base_dir.rglob(pattern))
    return sorted({file.resolve() for file in files if file.is_file()})


def _iter_pdf_documents(pdf_files: list[Path]) -> Iterable[Document]:
    """Yield PDF documents via pymupdf4llm to keep memory usage low."""
    for pdf_file in pdf_files:
        logger.info("Processing PDF {}", pdf_file.name)
        try:
            text_content = pymupdf4llm.to_markdown(str(pdf_file)).strip()
            if not text_content:
                logger.warning("No text extracted from {}", pdf_file.name)
                continue

            yield Document(
                page_content=text_content,
                metadata={
                    "source": pdf_file.name,
                    "file_path": str(pdf_file),
                    "file_type": "pdf",
                },
            )
        except Exception as e:
            logger.exception("Error processing PDF {}: {}", pdf_file.name, e)


def _iter_json_documents(json_files: list[Path]) -> Iterable[Document]:
    """Yield JSON documents to keep memory usage low."""

    for json_file in json_files:
        logger.info("Processing JSON {}", json_file.name)
        try:
            with json_file.open("r", encoding="utf-8") as f:
                payload = json.load(f)

            text_content = _json_to_text(payload).strip()
            if not text_content:
                logger.warning("No text extracted from {}", json_file.name)
                continue

            yield Document(
                page_content=text_content,
                metadata={
                    "source": json_file.name,
                    "file_path": str(json_file),
                    "file_type": "json",
                },
            )
        except Exception as e:
            logger.exception("Error processing JSON {}: {}", json_file.name, e)


def _upsert_chunks(
    vectorstore: FAISS | None,
    chunks: list[Document],
    embeddings: OpenAIEmbeddings,
    batch_size: int,
) -> FAISS | None:
    """Insert chunks into FAISS in small batches to avoid memory spikes."""
    if not chunks:
        return vectorstore

    total_batches = (len(chunks) - 1) // batch_size + 1
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        batch_number = i // batch_size + 1
        logger.info(
            "Embedding batch {}/{} ({} chunk(s))",
            batch_number,
            total_batches,
            len(batch),
        )

        if vectorstore is None:
            vectorstore = FAISS.from_documents(batch, embeddings)
        else:
            vectorstore.add_documents(batch)

    return vectorstore


def build_index():
    """Build FAISS index with OpenAI embedding model from knowledge base PDFs and JSON files."""
    project_root = PROJECT_ROOT
    kb_dir = project_root / "knowledge_base"

    if not kb_dir.exists():
        logger.warning("Knowledge base directory not found: {}", kb_dir)
        return

    pdf_files = _iter_files(kb_dir, ("*.pdf",))
    if MAX_PDFS > 0:
        pdf_files = pdf_files[:MAX_PDFS]

    if not pdf_files:
        logger.warning("No PDFs found in {}", kb_dir)

    json_files = _iter_files(kb_dir, ("*.json",))
    if MAX_JSON_FILES > 0:
        json_files = json_files[:MAX_JSON_FILES]

    if not json_files:
        logger.warning("No JSON files found in {}", kb_dir)

    if not pdf_files and not json_files:
        logger.warning("No source files found to index")
        return

    logger.info(
        "Found {} PDF file(s) and {} JSON file(s) to process",
        len(pdf_files),
        len(json_files),
    )

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", " ", ""],
    )
    logger.info("Embedding with OpenAI model {}", EMBEDDING_MODEL)

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to the project .env file or export it in your shell before running the indexer."
        )

    embeddings = OpenAIEmbeddings(
        model=EMBEDDING_MODEL,
        api_key=SecretStr(openai_api_key),
    )

    batch_size = DEFAULT_BATCH_SIZE
    logger.info("Processing in batches of {}", batch_size)

    vectorstore = None
    total_sources = 0
    total_chunks = 0

    for source_doc in _iter_pdf_documents(pdf_files):
        total_sources += 1
        try:
            chunks = text_splitter.split_documents([source_doc])
            total_chunks += len(chunks)
            vectorstore = _upsert_chunks(vectorstore, chunks, embeddings, batch_size)
        except Exception as e:
            logger.exception(
                "Failed to index PDF source {}: {}",
                source_doc.metadata.get("source"),
                e,
            )
            raise

    for source_doc in _iter_json_documents(json_files):
        total_sources += 1
        try:
            chunks = text_splitter.split_documents([source_doc])
            total_chunks += len(chunks)
            vectorstore = _upsert_chunks(vectorstore, chunks, embeddings, batch_size)
        except Exception as e:
            logger.exception(
                "Failed to index JSON source {}: {}",
                source_doc.metadata.get("source"),
                e,
            )
            raise

    if total_chunks == 0:
        logger.warning("No documents extracted")
        return

    logger.info("Loaded {} source document(s)", total_sources)
    logger.info("Created {} chunk(s) after splitting", total_chunks)

    index_dir = project_root / "knowledge_base"
    index_dir.mkdir(parents=True, exist_ok=True)

    if vectorstore is None:
        logger.error("Vector store was not created; nothing to save")
        return

    vectorstore.save_local(str(index_dir))

    logger.success("FAISS index built successfully")
    logger.info("Total chunks: {}", total_chunks)
    logger.info("Index saved to: {}", index_dir)


if __name__ == "__main__":
    build_index()
