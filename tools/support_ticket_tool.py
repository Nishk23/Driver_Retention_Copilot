import csv
from functools import lru_cache
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "support_tickets.csv"


@lru_cache(maxsize=1)
def _load_tickets() -> list[dict]:
    with DATA_PATH.open(newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _sort_recent(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda row: row.get("timestamp", ""), reverse=True)


def get_support_tickets(driver_id: str, limit: int = 10) -> list[dict]:
    normalized = (driver_id or "").strip().upper()
    rows = [row for row in _load_tickets() if row.get("driver_id", "").upper() == normalized]
    return _sort_recent(rows)[:limit]


def search_support_tickets(driver_id: str, query: str, limit: int = 10) -> list[dict]:
    normalized_query = query.lower().replace("/", " ").replace("_", " ")
    query_terms = [term for term in normalized_query.split() if len(term) > 2]
    rows = get_support_tickets(driver_id, limit=100)
    scored: list[tuple[int, dict]] = []
    for row in rows:
        haystack = " ".join(str(row.get(key, "")) for key in ["category", "message", "status"]).lower()
        score = sum(1 for term in query_terms if term in haystack)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: (item[0], item[1].get("timestamp", "")), reverse=True)
    return [row for _, row in scored[:limit]]
