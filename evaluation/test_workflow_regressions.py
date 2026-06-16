import json

from agents.strategist_agent import generate_retention_plan
from graph.workflow import normalize_issue_type, run_copilot


def test_airport_short_fare_normalization_handles_airport_names_and_codes():
    cases = [
        "Gatwick queue wait was 110 mins and short fare",
        "Heathrow queue for two hours and 1.5km trip",
        "LHR short fare again",
        "Airport queue short fare",
    ]
    for case in cases:
        assert normalize_issue_type(case) == "airport_short_fare"


def test_missing_driver_routes_to_manual_review_without_strategy():
    result = run_copilot(
        "Driver D-LON-999 called about airport queue short fare.",
        conversation_memory={},
        max_retries=0,
    )
    assert result["critic_verdict"]["status"] == "needs_review"
    assert "Needs manual review" in result["final_answer"]
    assert result.get("strategist_plan") is None


def test_strategist_keeps_zero_value_voucher_non_monetary(monkeypatch):
    raw_plan = {
        "risk_level": "high",
        "issue_type": "airport_short_fare",
        "reasoning": "Test plan.",
        "evidence_summary": ["Airport short fare evidence."],
        "proposed_actions": [
            {
                "action_type": "voucher",
                "amount": 0,
                "currency": "GBP",
                "description": "Airport Fast-Track Voucher",
                "incentive_id": "Q-103",
            }
        ],
        "manager_message": "Acknowledge the driver.",
        "assumptions": [],
    }

    monkeypatch.setattr("agents.strategist_agent.call_llm", lambda *_args, **_kwargs: json.dumps(raw_plan))
    plan = generate_retention_plan(
        {
            "user_query": "Driver Maria has an airport short fare.",
            "driver_profile": {"driver_id": "D-LON-001", "name": "Maria S.", "loyalty_tier": "Gold"},
            "support_tickets": [],
            "issue_type": "airport_short_fare",
            "incentive_options": {},
            "critic_verdict": None,
            "retry_count": 0,
        }
    )
    assert plan.proposed_actions[0].action_type == "future_quest"


def test_strategist_revises_rejected_short_fare_credit_to_policy_cap(monkeypatch):
    raw_plan = {
        "risk_level": "high",
        "issue_type": "airport_short_fare",
        "reasoning": "Test over-cap revision.",
        "evidence_summary": ["Airport short fare evidence."],
        "proposed_actions": [
            {
                "action_type": "credit",
                "amount": 50,
                "currency": "GBP",
                "reason": "LLM repeated the original over-cap amount.",
                "incentive_id": "INC-002",
            }
        ],
        "manager_message": "Acknowledge the driver.",
        "assumptions": [],
    }

    monkeypatch.setattr("agents.strategist_agent.call_llm", lambda *_args, **_kwargs: json.dumps(raw_plan))
    plan = generate_retention_plan(
        {
            "user_query": "Driver Maria has an airport short fare.",
            "driver_profile": {"driver_id": "D-LON-001", "name": "Maria S.", "loyalty_tier": "Gold"},
            "support_tickets": [],
            "issue_type": "airport_short_fare",
            "incentive_options": {},
            "critic_verdict": {
                "status": "rejected",
                "required_fixes": ["Reduce short_fare_credit to 25 GBP or below."],
            },
            "retry_count": 1,
        }
    )
    assert plan.proposed_actions[0].action_type == "short_fare_credit"
    assert plan.proposed_actions[0].amount == 25
