import copy
import json
from pathlib import Path

from tools.policy_rules import POLICY_CAPS
from tools.policy_validator import validate_plan_against_policy


ROOT = Path(__file__).resolve().parents[1]


def test_seeded_rejection_revision_approval_trace():
    invalid = json.loads((ROOT / "evaluation" / "seeded_invalid_plan.json").read_text())
    policy_chunks = [{"page": 1, "chunk_id": "seed", "text": "Gold airport short fare cap is GBP 25."}]

    rejected = validate_plan_against_policy(invalid, policy_chunks)
    assert rejected["status"] == "rejected"

    revised = copy.deepcopy(invalid)
    cap = POLICY_CAPS["short_fare_credit"]["max_amount"]
    for action in revised["proposed_actions"]:
        if action["action_type"] == "short_fare_credit":
            action["amount"] = cap
            action["reason"] = "Deterministically revised to the verified policy cap."

    approved = validate_plan_against_policy(revised, policy_chunks)
    assert approved["status"] == "approved"

    trace = [
        {"step": "seeded_invalid_plan", "status": "created"},
        {"step": "critic_verdict", "status": rejected["status"]},
        {"step": "deterministic_revision", "status": "revised"},
        {"step": "critic_verdict", "status": approved["status"]},
    ]
    assert [entry["status"] for entry in trace[1:]] == ["rejected", "revised", "approved"]
