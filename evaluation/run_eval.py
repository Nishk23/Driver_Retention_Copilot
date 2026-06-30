import copy
import json
import os
from pathlib import Path

from graph.workflow import run_copilot
from tools.policy_rules import POLICY_CAPS
from tools.policy_validator import validate_plan_against_policy


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "evaluation_trace.json"


def _seeded_self_correction() -> dict:
    invalid = json.loads((ROOT / "evaluation" / "seeded_invalid_plan.json").read_text())
    policy_chunks = [
        {
            "page": 1,
            "chunk_id": "seeded",
            "text": "Synthetic airport short fare policy cap: Gold drivers max 25 GBP.",
        }
    ]
    rejected = validate_plan_against_policy(invalid, policy_chunks)

    revised = copy.deepcopy(invalid)
    cap = POLICY_CAPS["short_fare_credit"]["max_amount"]
    for action in revised["proposed_actions"]:
        if action.get("action_type") == "short_fare_credit":
            action["amount"] = cap
            action["reason"] = "Deterministically revised to the verified policy cap."

    approved = validate_plan_against_policy(revised, policy_chunks)
    trace = [
        {"step": "seeded_invalid_plan", "data": invalid},
        {"step": "critic_verdict_seeded_invalid", "data": rejected},
        {"step": "deterministic_revision", "data": revised},
        {"step": "critic_verdict_seeded_revised", "data": approved},
    ]
    return {
        "passed": rejected["status"] == "rejected" and approved["status"] == "approved",
        "trace": trace,
    }


def main() -> None:
    test_cases = json.loads((ROOT / "evaluation" / "test_cases.json").read_text())
    seeded = _seeded_self_correction()
    live_runs = []

    if os.getenv("OPENROUTER_API_KEY") and os.getenv("MODEL_NAME"):
        for case in test_cases:
            live_runs.append({"id": case["id"], "result": run_copilot(case["query"])})
    else:
        live_runs.append({"skipped": "OPENROUTER_API_KEY or MODEL_NAME not configured; live workflow skipped."})

    payload = {
        "summary": {
            "seeded_self_correction_passed": seeded["passed"],
            "live_runs": len([run for run in live_runs if "result" in run]),
        },
        "seeded_self_correction_trace": seeded["trace"],
        "live_runs": live_runs,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload["summary"], indent=2))
    print(f"Saved evaluation trace to {OUTPUT}")


if __name__ == "__main__":
    main()
