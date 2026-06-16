import json
import os

from agents.prompts import CRITIC_SYSTEM_PROMPT
from llm.json_utils import parse_json_response
from llm.llm_client import call_llm
from state.schemas import CriticVerdict, DriverCopilotState
from tools.policy_rag_tool import search_policy
from tools.policy_rules import POLICY_CAPS
from tools.policy_validator import validate_plan_against_policy


def _policy_query_for_state(state: DriverCopilotState) -> str:
    issue_type = state.get("issue_type") or (state.get("strategist_plan") or {}).get("issue_type")
    if issue_type == "airport_short_fare":
        return POLICY_CAPS["short_fare_credit"]["policy_query"]
    if issue_type == "technical_issue":
        return POLICY_CAPS["technical_glitch_credit"]["policy_query"]
    return f"{issue_type or 'driver retention'} compensation policy cap guardrails"


def validate_retention_plan(state: DriverCopilotState) -> CriticVerdict:
    policy_chunks = search_policy(_policy_query_for_state(state), top_k=5)
    plan = dict(state.get("strategist_plan") or {})
    plan["driver_profile"] = state.get("driver_profile") or {}

    # Normalize action types coming from the Strategist so the deterministic
    # validator recognizes them. This maps common freeform action labels to the
    # canonical action types defined in `tools.policy_rules`.
    def _normalize_actions(plan: dict) -> dict:
        mapped = []
        issue_type = plan.get("issue_type")
        for action in plan.get("proposed_actions", []) or []:
            at = (action.get("action_type") or "").lower()
            incentive = (action.get("incentive_id") or "")
            new_at = at

            # Monetary synonyms that should map to a canonical monetary action.
            monetary_synonyms = {"credit", "incentive_credit", "incentive", "goodwill", "cash_credit", "compensation"}
            # Non-monetary synonyms mapping
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

            if at in non_monetary_map:
                new_at = non_monetary_map[at]
            elif at in monetary_synonyms or action.get("amount") is not None:
                # Prefer short_fare_credit when the issue is an airport short fare
                # or when the incentive id matches known short-fare incentives.
                short_fare_ids = {"INC-001", "INC-002"}
                if incentive in short_fare_ids or issue_type == "airport_short_fare":
                    new_at = "short_fare_credit"
                else:
                    new_at = "goodwill_credit"
            # leave unknowns as-is; validator will warn or require review
            new_action = dict(action)
            new_action["action_type"] = new_at
            mapped.append(new_action)
        new_plan = dict(plan)
        new_plan["proposed_actions"] = mapped
        return new_plan

    plan = _normalize_actions(plan)
    deterministic = validate_plan_against_policy(plan, policy_chunks)

    explanation = deterministic["explanation"]
    if os.getenv("OPENROUTER_API_KEY") and os.getenv("MODEL_NAME"):
        try:
            raw = call_llm(
                [
                    {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "plan": plan,
                                "policy_chunks": policy_chunks,
                                "deterministic_validator": deterministic,
                            },
                            indent=2,
                        ),
                    },
                ],
                temperature=0.0,
            )
            parsed = parse_json_response(raw)
            if isinstance(parsed, dict) and parsed.get("explanation"):
                explanation = parsed["explanation"]
        except Exception:
            explanation = deterministic["explanation"]

    return CriticVerdict(
        status=deterministic["status"],
        violations=deterministic["violations"],
        required_fixes=deterministic["required_fixes"],
        warnings=deterministic["warnings"],
        policy_evidence=deterministic["policy_evidence"],
        explanation=explanation,
    )
