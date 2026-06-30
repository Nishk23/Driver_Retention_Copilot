NON_MONETARY_ACTION_MAP = {
    "voucher": "future_quest",
    "fast_track": "future_quest",
    "airport_fast_track": "future_quest",
    "queue_fast_track": "future_quest",
    "queue_fast_track_voucher": "future_quest",
    "ticket_response": "support_escalation",
    "ticket_reply": "support_escalation",
    "outreach_call": "follow_up_call",
    "follow_up": "follow_up_call",
    "follow_up_call": "follow_up_call",
    "operations_escalation": "support_escalation",
    "escalate": "support_escalation",
    "escalate_ticket": "support_escalation",
    "flag_account": "support_escalation",
    "acknowledge": "manager_message",
    "apology": "apology_message",
    "monitoring": "monitor_driver",
    "monitor": "monitor_driver",
    "monitor_driver": "monitor_driver",
}

MONETARY_ACTION_SYNONYMS = {
    "credit",
    "incentive_credit",
    "incentive",
    "goodwill",
    "cash_credit",
    "compensation",
}

SHORT_FARE_INCENTIVE_IDS = {"INC-001", "INC-002"}


def normalize_plan_actions(plan: dict) -> dict:
    mapped = []
    issue_type = plan.get("issue_type")
    for action in plan.get("proposed_actions", []) or []:
        action_type = (action.get("action_type") or "").lower()
        incentive_id = action.get("incentive_id") or ""
        new_type = action_type

        if action_type in NON_MONETARY_ACTION_MAP:
            new_type = NON_MONETARY_ACTION_MAP[action_type]
        elif action_type in MONETARY_ACTION_SYNONYMS or action.get("amount") is not None:
            if incentive_id in SHORT_FARE_INCENTIVE_IDS or issue_type == "airport_short_fare":
                new_type = "short_fare_credit"
            else:
                new_type = "goodwill_credit"

        new_action = dict(action)
        new_action["action_type"] = new_type
        mapped.append(new_action)

    normalized = dict(plan)
    normalized["proposed_actions"] = mapped
    return normalized
