import os


COLLECTION_NAME = "freenow_policy_chunks"


def get_embedding_function():
    try:
        from chromadb.utils import embedding_functions
    except ImportError as exc:
        raise RuntimeError("chromadb is not installed. Run `pip install -r requirements.txt`.") from exc

    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    )


def load_or_create_vector_store(persist_dir: str):
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError("chromadb is not installed. Run `pip install -r requirements.txt`.") from exc

    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )
