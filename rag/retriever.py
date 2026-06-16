import json
import os
from pathlib import Path

from rag.ingest_policy import DEFAULT_PDF, FALLBACK_CHUNKS, build_policy_chunks
from rag.vector_store import load_or_create_vector_store


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PERSIST_DIR = PROJECT_ROOT / os.getenv("CHROMA_PERSIST_DIR", "./rag/chroma_db")


def _keyword_score(query: str, text: str) -> int:
    terms = [term for term in query.lower().replace("/", " ").split() if len(term) > 2]
    lowered = text.lower()
    return sum(lowered.count(term) for term in terms)


def _fallback_chunks() -> list[dict]:
    if FALLBACK_CHUNKS.exists():
        return json.loads(FALLBACK_CHUNKS.read_text())
    if DEFAULT_PDF.exists():
        return build_policy_chunks(str(DEFAULT_PDF))
    return []


def _keyword_retrieve(query: str, top_k: int) -> list[dict]:
    scored = []
    for chunk in _fallback_chunks():
        score = _keyword_score(query, chunk.get("text", ""))
        if score:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return _fallback_chunks()[:top_k]
    return [
        {
            "chunk_id": chunk.get("chunk_id") or chunk.get("id"),
            "page": chunk.get("page"),
            "text": chunk.get("text", ""),
            "score": float(score),
        }
        for score, chunk in scored[:top_k]
    ]


def retrieve_policy_chunks(query: str, top_k: int = 5) -> list[dict]:
    try:
        collection = load_or_create_vector_store(str(DEFAULT_PERSIST_DIR))
        if collection.count() == 0:
            return _keyword_retrieve(query, top_k)
        result = collection.query(query_texts=[query], n_results=top_k)
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        chunks = []
        for doc, metadata, distance in zip(documents, metadatas, distances):
            chunks.append(
                {
                    "chunk_id": metadata.get("chunk_id"),
                    "page": metadata.get("page"),
                    "text": doc,
                    "score": None if distance is None else float(distance),
                }
            )
        return chunks
    except Exception:
        return _keyword_retrieve(query, top_k)
