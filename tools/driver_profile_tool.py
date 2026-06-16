import json
import re
from functools import lru_cache
from pathlib import Path


DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "driver_profiles.json"


@lru_cache(maxsize=1)
def _load_profiles() -> list[dict]:
    return json.loads(DATA_PATH.read_text())


def get_driver_profile(driver_id: str) -> dict:
    normalized = (driver_id or "").strip().upper()
    for profile in _load_profiles():
        if profile.get("driver_id", "").upper() == normalized:
            return dict(profile)
    return {"error": f"Driver profile not found for driver_id={driver_id}."}


def find_driver_by_name(name: str) -> dict | None:
    if not name:
        return None
    cleaned = re.sub(r"[^a-z ]", " ", name.lower()).strip()
    if not cleaned:
        return None
    tokens = [t for t in cleaned.split() if len(t) > 1]
    for profile in _load_profiles():
        profile_name = profile.get("name", "").lower()
        if cleaned in profile_name or all(token in profile_name for token in tokens[:2]):
            return dict(profile)
    first = tokens[0] if tokens else cleaned
    for profile in _load_profiles():
        if first and first in profile.get("name", "").lower():
            return dict(profile)
    return None
