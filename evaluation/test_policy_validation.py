from tools.policy_validator import validate_plan_against_policy


POLICY_CHUNKS = [{"page": 1, "chunk_id": "test", "text": "Airport Short Fares GOLD TIER CAP: GBP 25."}]


def plan(actions, tier="Gold"):
    return {
        "issue_type": "airport_short_fare",
        "driver_profile": {"loyalty_tier": tier},
        "proposed_actions": actions,
    }


def test_credit_above_cap_is_rejected():
    result = validate_plan_against_policy(
        plan([{"action_type": "short_fare_credit", "amount": 50, "currency": "GBP"}]),
        POLICY_CHUNKS,
    )
    assert result["status"] == "rejected"
    assert result["violations"][0]["allowed_amount"] == 25


def test_credit_equal_to_cap_is_approved():
    result = validate_plan_against_policy(
        plan([{"action_type": "short_fare_credit", "amount": 25, "currency": "GBP"}]),
        POLICY_CHUNKS,
    )
    assert result["status"] == "approved"


def test_missing_policy_evidence_still_enforces_cap():
    result = validate_plan_against_policy(
        plan([{"action_type": "short_fare_credit", "amount": 50, "currency": "GBP"}]),
        [],
    )
    assert result["status"] == "rejected"


def test_unknown_monetary_action_returns_needs_review():
    result = validate_plan_against_policy(
        plan([{"action_type": "custom_cash_payout", "amount": 5, "currency": "GBP"}]),
        POLICY_CHUNKS,
    )
    assert result["status"] == "needs_review"


def test_known_non_monetary_action_does_not_force_needs_review():
    result = validate_plan_against_policy(
        plan([{"action_type": "manager_message", "description": "Acknowledge issue."}]),
        POLICY_CHUNKS,
    )
    assert result["status"] == "approved"


def test_corrected_multi_action_plan_is_approved():
    result = validate_plan_against_policy(
        plan(
            [
                {"action_type": "short_fare_credit", "amount": 25, "currency": "GBP"},
                {"action_type": "future_quest", "description": "Airport Recovery Quest for tomorrow"},
                {"action_type": "manager_message", "description": "Personally acknowledge the issue."},
            ]
        ),
        POLICY_CHUNKS,
    )
    assert result["status"] == "approved"
    assert result["violations"] == []
