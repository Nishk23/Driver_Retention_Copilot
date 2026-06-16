import json

from agents.prompts import STRATEGIST_SYSTEM_PROMPT
from llm.json_utils import parse_json_response
from llm.llm_client import call_llm
from state.schemas import DriverCopilotState, RetentionPlan
from tools.policy_rules import POLICY_CAPS


def _risk_level(profile: dict, issue_type: str) -> str:
    sentiment = (profile.get("recent_sentiment") or "").lower()
    short_fares = int(profile.get("airport_short_fare_count_30d") or 0)
    if issue_type == "airport_short_fare" and (short_fares >= 3 or "angry" in sentiment or "frustrated" in sentiment):
        return "high"
    if profile.get("current_status") == "OFFLINE" or "upset" in sentiment:
        return "medium"
    return "low"


def _matching_incentive(options: dict, *ids: str) -> dict | None:
    for incentive in options.get("incentives", []):
        if incentive.get("id") in ids:
            return incentive
    return None


def _short_fare_cap_for_profile(profile: dict) -> float:
    return POLICY_CAPS["short_fare_credit"]["tier_caps"].get(
        profile.get("loyalty_tier"), POLICY_CAPS["short_fare_credit"]["max_amount"]
    )


def _apply_deterministic_revision(parsed_plan: dict, state: DriverCopilotState) -> dict:
    verdict = state.get("critic_verdict") or {}
    if verdict.get("status") != "rejected":
        return parsed_plan

    cap = _short_fare_cap_for_profile(state.get("driver_profile") or {})
    revised = dict(parsed_plan)
    actions = []
    for action in revised.get("proposed_actions") or []:
        updated = dict(action)
        if updated.get("action_type") == "short_fare_credit" and updated.get("amount") is not None:
            if float(updated["amount"]) > cap:
                updated["amount"] = cap
                updated["currency"] = "GBP"
                updated["reason"] = (
                    f"Deterministically revised after critic feedback to comply with the {cap:.0f} GBP "
                    "airport short-fare compensation cap."
                )
        actions.append(updated)
    revised["proposed_actions"] = actions
    assumptions = list(revised.get("assumptions") or [])
    assumptions.append("Applied deterministic cap correction after Compliance Critic rejection.")
    revised["assumptions"] = assumptions
    return revised


def _deterministic_plan(state: DriverCopilotState) -> RetentionPlan:
    profile = state.get("driver_profile") or {}
    issue_type = state.get("issue_type") or "unknown"
    tickets = state.get("support_tickets") or []
    incentives = state.get("incentive_options") or {}
    verdict = state.get("critic_verdict") or {}
    retry_count = state.get("retry_count", 0)
    risk = _risk_level(profile, issue_type)

    evidence = [
        f"Profile sentiment: {profile.get('recent_sentiment', 'not available')}",
        f"Airport short-fare count in 30d: {profile.get('airport_short_fare_count_30d', 'not available')}",
    ]
    evidence.extend(
        f"{ticket.get('ticket_id')}: {ticket.get('category')} - {ticket.get('message')}"
        for ticket in tickets[:3]
    )

    actions: list[dict] = []
    assumptions: list[str] = []
    if issue_type == "airport_short_fare":
        cap = _short_fare_cap_for_profile(profile)
        premium = _matching_incentive(incentives, "INC-002")
        standard = _matching_incentive(incentives, "INC-001")
        if retry_count == 0 and profile.get("loyalty_tier") == "Gold" and premium:
            amount = float(premium["value"])
            incentive_id = premium["id"]
            reason = "Initial retention-optimized proposal using the premium airport recovery incentive."
        else:
            amount = cap
            incentive_id = standard["id"] if standard else None
            reason = "Revised or policy-aware airport short-fare recovery within deterministic cap."

        actions.append(
            {
                "action_type": "short_fare_credit",
                "amount": amount,
                "currency": "GBP",
                "incentive_id": incentive_id,
                "reason": reason,
            }
        )
        quest = _matching_incentive(incentives, "Q-103", "Q-101")
        actions.append(
            {
                "action_type": "future_quest",
                "description": (quest or {}).get("name", "Airport recovery quest for tomorrow"),
                "incentive_id": (quest or {}).get("id"),
                "reason": "Encourage the driver to re-engage after the poor airport experience.",
            }
        )
    elif issue_type == "technical_issue":
        actions.append(
            {
                "action_type": "technical_glitch_credit",
                "amount": 10,
                "currency": "GBP",
                "incentive_id": "INC-003",
                "reason": "Confirmed technical/GPS issue compensation.",
            }
        )
        actions.append({"action_type": "priority_support", "description": "Escalate recurring geofence issue."})
    else:
        actions.append(
            {
                "action_type": "support_escalation",
                "description": "Escalate to Driver Relationship Manager for manual assessment.",
            }
        )
        assumptions.append("Issue type is not covered by a deterministic compensation rule.")

    actions.extend(
        [
            {
                "action_type": "manager_message",
                "description": "Manager should personally acknowledge the repeated issue and confirm the recovery action.",
            },
            {
                "action_type": "monitor_driver",
                "description": "Monitor status and support tickets for 7 days after the recovery action.",
            },
        ]
    )

    if verdict.get("status") == "rejected":
        assumptions.append(f"Plan revised after critic feedback: {verdict.get('required_fixes')}")

    return RetentionPlan(
        risk_level=risk,
        issue_type=issue_type,
        reasoning=(
            "The driver shows retention risk based on current sentiment, repeated complaint pattern, "
            "and actual ticket evidence."
        ),
        evidence_summary=evidence,
        proposed_actions=actions,
        manager_message=(
            f"Acknowledge {profile.get('name', 'the driver')}'s repeated issue, explain the policy-compliant recovery, "
            "and confirm follow-up monitoring."
        ),
        assumptions=assumptions,
    )


def generate_retention_plan(state: DriverCopilotState) -> RetentionPlan:
    prompt_payload = {
        "user_query": state.get("user_query"),
        "driver_profile": state.get("driver_profile"),
        "support_tickets": state.get("support_tickets"),
        "issue_type": state.get("issue_type"),
        "incentive_options": state.get("incentive_options"),
        "critic_feedback": state.get("critic_verdict"),
    }
    try:
        raw = call_llm(
            [
                {"role": "system", "content": STRATEGIST_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(prompt_payload, indent=2)},
            ],
            temperature=0.2,
        )
        parsed = parse_json_response(raw, RetentionPlan)
        if parsed.get("status") == "needs_review":
            raise ValueError(parsed.get("error", "LLM JSON parse failed."))

        # Normalize action_type values from the LLM to canonical types used
        # by the system so downstream validators can operate deterministically.
        def _normalize_plan_actions(parsed_plan: dict) -> dict:
            mapped = []
            issue_type = parsed_plan.get("issue_type")
            for action in (parsed_plan.get("proposed_actions") or []):
                at = (action.get("action_type") or "").lower()
                incentive = action.get("incentive_id") or ""
                new_at = at

                non_monetary_map = {
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
                monetary_synonyms = {"credit", "incentive_credit", "incentive", "goodwill", "cash_credit", "compensation"}
                short_fare_ids = {"INC-001", "INC-002"}
                if at in non_monetary_map:
                    new_at = non_monetary_map[at]
                elif at in monetary_synonyms or action.get("amount") is not None:
                    if incentive in short_fare_ids or issue_type == "airport_short_fare":
                        new_at = "short_fare_credit"
                    else:
                        new_at = "goodwill_credit"

                new_action = dict(action)
                new_action["action_type"] = new_at
                mapped.append(new_action)

            new_parsed = dict(parsed_plan)
            new_parsed["proposed_actions"] = mapped
            return new_parsed

        parsed = _normalize_plan_actions(parsed)
        parsed = _apply_deterministic_revision(parsed, state)
        return RetentionPlan.model_validate(parsed)
    except Exception:
        return _deterministic_plan(state)
