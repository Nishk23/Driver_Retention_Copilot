POLICY_CAPS = {
    "global_monthly": {
        "max_amount": 150.0,
        "currency": "GBP",
        "policy_query": "global monthly cap automated retention package total value driver calendar month",
        "description": "Global monthly automated retention cap",
    },
    "short_fare_credit": {
        "max_amount": 25.0,
        "tier_caps": {"Gold": 25.0, "Silver": 15.0, "Bronze": 15.0},
        "currency": "GBP",
        "policy_query": "airport short fare compensation cap queue wait distance",
        "description": "Airport Short Fare compensation cap",
    },
    "technical_glitch_credit": {
        "max_amount": 10.0,
        "currency": "GBP",
        "policy_query": "Technical GPS glitches maximum compensation confirmed glitch",
        "description": "Technical/GPS glitch compensation cap",
    },
}

MONETARY_ACTION_TYPES = {
    "short_fare_credit",
    "cash_credit",
    "compensation",
    "refund",
    "bonus_credit",
    "technical_glitch_credit",
    "goodwill_credit",
}

NON_MONETARY_ALLOWLIST = {
    "manager_message",
    "apology_message",
    "follow_up_call",
    "monitor_driver",
    "future_quest",
    "airport_recovery_quest",
    "support_escalation",
    "education_message",
    "priority_support",
}

ISSUE_TYPE_ENUM = {
    "airport_short_fare",
    "bonus_confusion",
    "technical_issue",
    "low_earnings",
    "support_delay",
    "unknown",
}
