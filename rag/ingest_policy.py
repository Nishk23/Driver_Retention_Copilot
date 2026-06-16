import json
import os
from pathlib import Path

from rag.vector_store import load_or_create_vector_store


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PDF = PROJECT_ROOT / "data" / "freenow_policies.pdf"
DEFAULT_PERSIST_DIR = PROJECT_ROOT / os.getenv("CHROMA_PERSIST_DIR", "./rag/chroma_db")
FALLBACK_CHUNKS = PROJECT_ROOT / "rag" / "policy_chunks.json"


def extract_pdf_text(pdf_path: str) -> list[dict]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is not installed. Run `pip install -r requirements.txt`.") from exc

    reader = PdfReader(pdf_path)
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        pages.append({"page": index, "text": page.extract_text() or ""})
    return pages


def chunk_text(text: str, chunk_size: int = 2600, overlap: int = 400) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return chunks


def build_policy_chunks(pdf_path: str) -> list[dict]:
    records: list[dict] = []
    for page in extract_pdf_text(pdf_path):
        for idx, chunk in enumerate(chunk_text(page["text"]), start=1):
            records.append(
                {
                    "id": f"page-{page['page']}-chunk-{idx}",
                    "chunk_id": f"page-{page['page']}-chunk-{idx}",
                    "page": page["page"],
                    "text": chunk,
                }
            )
    return records


def ingest_policy_pdf(pdf_path: str = str(DEFAULT_PDF), persist_dir: str = str(DEFAULT_PERSIST_DIR)) -> None:
    chunks = build_policy_chunks(pdf_path)
    FALLBACK_CHUNKS.write_text(json.dumps(chunks, indent=2))

    collection = load_or_create_vector_store(persist_dir)
    if chunks:
        collection.upsert(
            ids=[chunk["id"] for chunk in chunks],
            documents=[chunk["text"] for chunk in chunks],
            metadatas=[{"page": chunk["page"], "chunk_id": chunk["chunk_id"]} for chunk in chunks],
        )


if __name__ == "__main__":
    ingest_policy_pdf()
    print(f"Ingested policy PDF into {DEFAULT_PERSIST_DIR}")
