from rag.retriever import retrieve_policy_chunks


def search_policy(query: str, top_k: int = 5) -> list[dict]:
    return retrieve_policy_chunks(query, top_k=top_k)
