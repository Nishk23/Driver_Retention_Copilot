import json
import re
from pathlib import Path
from typing import Any


MEMORY_DIR = Path("outputs/memory")


def _memory_path(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id)
    return MEMORY_DIR / f"{safe}.json"


def load_memory(session_id: str | None) -> dict:
    if not session_id:
        return {}
    path = _memory_path(session_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def save_memory(session_id: str | None, memory: dict) -> None:
    if not session_id:
        return
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    _memory_path(session_id).write_text(json.dumps(memory, indent=2))


def update_memory(memory: dict, state: dict[str, Any]) -> dict:
    updated = dict(memory or {})
    if state.get("driver_id"):
        updated["last_driver_id"] = state["driver_id"]
    if state.get("driver_name"):
        updated["last_driver_name"] = state["driver_name"]
    if state.get("issue_type"):
        updated["last_issue_type"] = state["issue_type"]
    if state.get("strategist_plan"):
        updated["last_plan"] = state["strategist_plan"]
    return updated


def resolve_context_from_memory(user_query: str, memory: dict) -> dict:
    lowered = user_query.lower()
    context: dict[str, Any] = {}
    pronoun_reference = any(token in lowered for token in [" her ", " his ", " their ", " them ", " driver "])
    if pronoun_reference and memory.get("last_driver_id"):
        context["driver_id"] = memory["last_driver_id"]
        context["driver_name"] = memory.get("last_driver_name")
    if memory.get("last_issue_type") and "policy" in lowered:
        context["issue_type"] = memory["last_issue_type"]
    return context
