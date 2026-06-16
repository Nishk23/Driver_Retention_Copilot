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
