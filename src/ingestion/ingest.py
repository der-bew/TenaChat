import os
import asyncio
from docling.document_converter import DocumentConverter
from docling.datamodel.base_models import ConversionStatus
from langchain_google_vertexai import VertexAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from pathlib import Path
import pickle

# Configuration
KNOWLEDGE_BASE_DIR = "knowledge_base/data"
VECTOR_STORE_PATH = "vector_store/faiss_index"
EMBEDDING_MODEL = "text-embedding-004"  # Google Embeddings 2 model
PROJECT_ID = "your-gcp-project-id"  # Replace with your project ID
LOCATION = "us-central1"


async def process_pdf_files():
    """Process PDF files using Docling and extract text."""
    converter = DocumentConverter()
    all_texts = []
    source_files = []

    # Iterate through PDF files in the knowledge base
    for pdf_file in Path(KNOWLEDGE_BASE_DIR).glob("*.pdf"):
        print(f"Processing: {pdf_file.name}")
        try:
            # Convert document
            result = converter.convert(pdf_file)
            if result.status == ConversionStatus.SUCCESS:
                # Extract text content
                text_content = result.document.export_to_markdown()
                all_texts.append(text_content)
                source_files.append(str(pdf_file))
                print(f"Successfully processed: {pdf_file.name}")
            else:
                print(f"Failed to process: {pdf_file.name}")
        except Exception as e:
            print(f"Error processing {pdf_file.name}: {str(e)}")

    return all_texts, source_files


def split_text(texts, chunk_size=1000, chunk_overlap=200):
    """Split text into chunks for better retrieval."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=False,
    )
    chunks = text_splitter.create_documents(texts)
    return chunks


def create_vector_store(documents, embeddings, store_path):
    """Create and save FAISS vector store."""
    # Create FAISS index
    vector_store = FAISS.from_documents(documents, embeddings)

    # Save the vector store
    os.makedirs(os.path.dirname(store_path), exist_ok=True)
    vector_store.save_local(store_path)
    print(f"Vector store saved to: {store_path}")

    return vector_store


async def main():
    """Main ingestion pipeline."""
    print("Starting RAG ingestion pipeline...")

    # Step 1: Process PDF files
    print("\n1. Processing PDF files with Docling...")
    texts, sources = await process_pdf_files()
    if not texts:
        print("No texts extracted. Check PDF files.")
        return

    # Step 2: Split text into chunks
    print("\n2. Splitting text into chunks...")
    documents = split_text(texts)
    print(f"Created {len(documents)} chunks")

    # Step 3: Initialize Google Embeddings
    print("\n3. Initializing Google Embeddings 2...")
    # For Vertex AI embeddings
    embeddings = VertexAIEmbeddings(
        model_name=EMBEDDING_MODEL, project=PROJECT_ID, location=LOCATION
    )

    # Step 4: Create vector store
    print("\n4. Creating vector store...")
    vector_store = create_vector_store(documents, embeddings, VECTOR_STORE_PATH)

    print("\nIngestion complete!")
    return vector_store


if __name__ == "__main__":
    asyncio.run(main())
