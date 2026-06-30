from tools.policy_validator import validate_plan_against_policy


POLICY_CHUNKS = [
    {
        "page": 1,
        "chunk_id": "test",
        "text": "Synthetic airport short fare policy cap: Gold drivers max 25 GBP.",
    }
]


def plan(actions, tier="Gold"):
    return {
        "issue_type": "airport_short_fare",
        "driver_profile": {"loyalty_tier": tier},
        "user_query": "Driver waited 120 minutes at Heathrow for a 1.5km short fare.",
        "incentive_options": {
            "incentives": [
                {"id": "INC-001", "value": 25.0, "currency": "GBP"},
                {"id": "INC-003", "value": 10.0, "currency": "GBP"},
            ]
        },
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


def test_silver_and_bronze_short_fare_cap_is_15_gbp():
    for tier in ("Silver", "Bronze"):
        result = validate_plan_against_policy(
            plan([{"action_type": "short_fare_credit", "amount": 25, "currency": "GBP"}], tier=tier),
            POLICY_CHUNKS,
        )
        assert result["status"] == "rejected"
        assert result["violations"][0]["allowed_amount"] == 15


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


def test_global_monthly_cap_is_rejected():
    result = validate_plan_against_policy(
        {
            "issue_type": "technical_issue",
            "driver_profile": {"loyalty_tier": "Gold"},
            "proposed_actions": [
                {"action_type": "technical_glitch_credit", "amount": 10, "currency": "GBP"},
                {"action_type": "goodwill_credit", "amount": 145, "currency": "GBP"},
            ],
        },
        POLICY_CHUNKS,
    )
    assert result["status"] == "rejected"
    assert result["violations"][0]["allowed_amount"] == 150


def test_unknown_incentive_id_requires_review():
    result = validate_plan_against_policy(
        plan([{"action_type": "short_fare_credit", "amount": 15, "currency": "GBP", "incentive_id": "INC-999"}]),
        POLICY_CHUNKS,
    )
    assert result["status"] == "needs_review"
    assert "INC-999" in result["warnings"][0]


def test_explicit_short_fare_ineligible_wait_is_rejected():
    result = validate_plan_against_policy(
        {
            "issue_type": "airport_short_fare",
            "driver_profile": {"loyalty_tier": "Gold"},
            "user_query": "Driver waited 60 minutes at Heathrow for a 1.5km trip.",
            "proposed_actions": [{"action_type": "short_fare_credit", "amount": 10, "currency": "GBP"}],
        },
        POLICY_CHUNKS,
    )
    assert result["status"] == "rejected"
    assert "greater than 90" in result["required_fixes"][0]
