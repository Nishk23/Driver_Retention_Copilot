import json
import os
import re
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


def _clean_policy_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _split_long_segment(segment: str, max_chars: int) -> list[str]:
    if len(segment) <= max_chars:
        return [segment]

    sentences = re.split(r"(?<=[.)])\s+", segment)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def chunk_text(text: str, max_chars: int = 700) -> list[str]:
    clean = _clean_policy_text(text)
    if not clean:
        return []

    starts = [
        match.start()
        for match in re.finditer(r"(?:Section\s+[A-Z]:|\s\d+\.\s+[A-Z])", clean)
    ]
    if not starts:
        return _split_long_segment(clean, max_chars)

    chunks: list[str] = []
    if starts[0] > 0:
        title = clean[: starts[0]].strip()
        if title:
            chunks.append(title)

    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(clean)
        segment = clean[start:end].strip()
        if segment:
            chunks.extend(_split_long_segment(segment, max_chars))
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
