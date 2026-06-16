import json
import os
import re
from pathlib import Path
from typing import Literal

from agents.compliance_critic_agent import validate_retention_plan
from agents.strategist_agent import generate_retention_plan
from state.memory import resolve_context_from_memory
from state.schemas import DriverCopilotState
from tools.driver_profile_tool import find_driver_by_name, get_driver_profile
from tools.incentive_tool import calculate_retention_options
from tools.support_ticket_tool import get_support_tickets, search_support_tickets


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRACE_PATH = PROJECT_ROOT / "outputs" / "evaluation_trace.json"


def normalize_issue_type(text: str) -> str:
    lowered = (text or "").lower()
    if "airport" in lowered and ("short" in lowered or "1.5km" in lowered or "1.5 km" in lowered or "queue" in lowered):
        return "airport_short_fare"
    if "bonus" in lowered or "incentive" in lowered or "quest" in lowered:
        return "bonus_confusion"
    if "app" in lowered or "technical" in lowered or "bug" in lowered or "gps" in lowered or "geofence" in lowered:
        return "technical_issue"
    if "earning" in lowered or "low fare" in lowered or "low earnings" in lowered:
        return "low_earnings"
    if "support" in lowered or "ticket" in lowered:
        return "support_delay"
    return "unknown"


def _extract_name(query: str) -> str | None:
    match = re.search(r"\bDriver\s+([A-Z][a-zA-Z.'-]+)", query)
    if match:
        return match.group(1)
    for profile_name in re.findall(r"\b([A-Z][a-zA-Z.'-]+)\b", query):
        if profile_name.lower() not in {"driver", "freenow"}:
            return profile_name
    return None


def extract_context_node(state: DriverCopilotState) -> dict:
    query = state.get("user_query", "")
    memory_context = resolve_context_from_memory(query, state.get("conversation_memory") or {})
    id_match = re.search(r"\bD-(?:[A-Z]+-)?\d+\b", query, flags=re.IGNORECASE)
    driver_id = id_match.group(0).upper() if id_match else memory_context.get("driver_id")
    driver_name = _extract_name(query) or memory_context.get("driver_name")
    issue_type = normalize_issue_type(query)
    if issue_type == "unknown" and memory_context.get("issue_type"):
        issue_type = memory_context["issue_type"]
    return {
        "driver_id": driver_id,
        "driver_name": driver_name,
        "issue_type": issue_type,
        "trace": [
            {
                "step": "context_extraction",
                "data": {"driver_id": driver_id, "driver_name": driver_name, "issue_type": issue_type},
            }
        ],
    }


def load_driver_profile_node(state: DriverCopilotState) -> dict:
    profile = get_driver_profile(state.get("driver_id") or "") if state.get("driver_id") else {}
    if profile.get("error") and state.get("driver_name"):
        by_name = find_driver_by_name(state["driver_name"])
        if by_name:
            profile = by_name
    elif not profile and state.get("driver_name"):
        profile = find_driver_by_name(state["driver_name"]) or {}

    if not profile or profile.get("error"):
        return {
            "driver_profile": profile,
            "trace": [{"step": "driver_profile_retrieval", "data": {"status": "missing", "profile": profile}}],
        }
    return {
        "driver_id": profile.get("driver_id"),
        "driver_name": profile.get("name"),
        "driver_profile": profile,
        "trace": [
            {
                "step": "driver_profile_retrieval",
                "data": {
                    "status": "found",
                    "driver_id": profile.get("driver_id"),
                    "name": profile.get("name"),
                    "tier": profile.get("loyalty_tier"),
                },
            }
        ],
    }


def load_support_tickets_node(state: DriverCopilotState) -> dict:
    driver_id = state.get("driver_id")
    if not driver_id:
        return {"support_tickets": [], "trace": [{"step": "support_ticket_retrieval", "data": {"count": 0}}]}
    issue_query = {
        "airport_short_fare": "airport short fare queue Heathrow Gatwick LHR",
        "technical_issue": "technical app gps geofence glitch crash",
        "bonus_confusion": "bonus incentive quest commission",
        "low_earnings": "earnings low fare payment",
        "support_delay": "support ticket delay",
    }
    query = issue_query.get(state.get("issue_type") or "", state.get("user_query", ""))
    tickets = search_support_tickets(driver_id, query, limit=10) or get_support_tickets(driver_id, limit=10)
    return {
        "support_tickets": tickets,
        "trace": [{"step": "support_ticket_retrieval", "data": {"count": len(tickets), "tickets": tickets[:5]}}],
    }


def load_incentives_node(state: DriverCopilotState) -> dict:
    profile = state.get("driver_profile") or {}
    if not state.get("driver_id") or profile.get("error"):
        options = {"error": "Cannot load incentives without a valid driver profile."}
    else:
        options = calculate_retention_options(state["driver_id"], state.get("issue_type") or "unknown", profile)
    return {
        "incentive_options": options,
        "trace": [{"step": "incentive_retrieval", "data": options}],
    }


def strategist_node(state: DriverCopilotState) -> dict:
    plan = generate_retention_plan(state).model_dump()
    return {
        "strategist_plan": plan,
        "risk_level": plan.get("risk_level"),
        "issue_type": normalize_issue_type(plan.get("issue_type") or state.get("issue_type") or ""),
        "trace": [
            {
                "step": f"strategist_plan_v{state.get('retry_count', 0) + 1}",
                "data": plan,
            }
        ],
    }


def critic_node(state: DriverCopilotState) -> dict:
    verdict = validate_retention_plan(state).model_dump()
    return {
        "critic_verdict": verdict,
        "retrieved_policy_chunks": verdict.get("policy_evidence", []),
        "trace": [
            {
                "step": f"critic_verdict_v{state.get('retry_count', 0) + 1}",
                "data": verdict,
            }
        ],
    }


def revision_router(state: DriverCopilotState) -> Literal[
    "final_response_node", "increment_retry_node", "safe_fallback_final_response_node"
]:
    verdict = state.get("critic_verdict") or {}
    status = verdict.get("status")
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)

    if status == "approved":
        return "final_response_node"
    if status == "needs_review":
        return "safe_fallback_final_response_node"
    if status == "rejected" and retry_count < max_retries:
        return "increment_retry_node"
    return "safe_fallback_final_response_node"


def increment_retry_node(state: DriverCopilotState) -> dict:
    next_retry = state.get("retry_count", 0) + 1
    return {
        "retry_count": next_retry,
        "trace": [
            {
                "step": "retry_incremented",
                "data": {
                    "retry_count": next_retry,
                    "reason": "Critic rejected the previous plan. Routing back to Strategist for revision.",
                },
            }
        ],
    }


def _actions_text(plan: dict) -> list[str]:
    lines = []
    for action in plan.get("proposed_actions", []):
        amount = action.get("amount")
        amount_text = f" ({amount:.0f} {action.get('currency', 'GBP')})" if isinstance(amount, (int, float)) else ""
        desc = action.get("description") or action.get("reason") or ""
        lines.append(f"- {action.get('action_type')}{amount_text}: {desc}")
    return lines


def final_response_node(state: DriverCopilotState) -> dict:
    profile = state.get("driver_profile") or {}
    plan = state.get("strategist_plan") or {}
    verdict = state.get("critic_verdict") or {}
    rejected = [
        entry for entry in state.get("trace", []) if entry.get("step", "").startswith("critic_verdict") and entry.get("data", {}).get("status") == "rejected"
    ]
    answer_lines = [
        "Driver Retention Recommendation",
        "",
        "Driver:",
        f"- Name: {profile.get('name', 'Unknown')}",
        f"- Driver ID: {profile.get('driver_id', state.get('driver_id') or 'Unknown')}",
        f"- Tier: {profile.get('loyalty_tier', 'Unknown')}",
        f"- Risk level: {plan.get('risk_level', 'unknown')}",
        "",
        "Situation:",
        f"- Issue type: {plan.get('issue_type', state.get('issue_type', 'unknown'))}",
        f"- Summary: {plan.get('reasoning', 'No reasoning available.')}",
        "- Evidence from support tickets:",
    ]
    answer_lines.extend([f"  - {item}" for item in plan.get("evidence_summary", [])[:5]] or ["  - No matching tickets found."])
    answer_lines.extend(["", "Recommended Plan:"])
    answer_lines.extend(_actions_text(plan))
    answer_lines.extend(
        [
            f"- Manager message: {plan.get('manager_message', 'No message generated.')}",
            "- Monitoring recommendation: Monitor driver activity and new support tickets for 7 days.",
            "",
            "Compliance Validation:",
            f"- Status: {verdict.get('status', 'needs_review')}",
            f"- Policy evidence: {verdict.get('explanation', 'No explanation available.')}",
        ]
    )
    if rejected:
        last_rejection = rejected[-1]["data"]
        answer_lines.append(f"- Rejected previous action: {last_rejection.get('violations')}")
        answer_lines.append(f"- Correction made: {last_rejection.get('required_fixes')}")
    else:
        answer_lines.append("- Rejected previous action: None")
        answer_lines.append("- Correction made: None required")
    answer_lines.extend(["", "Final Decision:", "- Approved"])
    final_answer = "\n".join(answer_lines)
    return {"final_answer": final_answer, "trace": [{"step": "final_response", "data": {"final_answer": final_answer}}]}


def safe_fallback_final_response_node(state: DriverCopilotState) -> dict:
    verdict = state.get("critic_verdict") or {}
    final_answer = "\n".join(
        [
            "Driver Retention Recommendation",
            "",
            "Final Decision:",
            "- Needs manual review",
            "",
            "Reason:",
            f"- {verdict.get('explanation', 'The system could not safely approve this plan.')}",
            f"- Required fixes: {verdict.get('required_fixes', [])}",
            f"- Warnings: {verdict.get('warnings', [])}",
        ]
    )
    return {
        "final_answer": final_answer,
        "trace": [{"step": "safe_fallback_final_response", "data": {"final_answer": final_answer}}],
    }


def save_trace_node(state: DriverCopilotState) -> dict:
    TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRACE_PATH.write_text(
        json.dumps(
            {
                "trace": state.get("trace", []),
                "final_answer": state.get("final_answer"),
                "driver_id": state.get("driver_id"),
                "issue_type": state.get("issue_type"),
            },
            indent=2,
        )
    )
    return {"trace": [{"step": "trace_saved", "data": {"path": str(TRACE_PATH)}}]}


def _fallback_run(initial_state: DriverCopilotState) -> DriverCopilotState:
    state = {**initial_state, "trace": list(initial_state.get("trace", []))}
    for node in [extract_context_node, load_driver_profile_node, load_support_tickets_node, load_incentives_node]:
        result = node(state)
        state.update({k: v for k, v in result.items() if k != "trace"})
        state["trace"].extend(result.get("trace", []))

    while True:
        for node in [strategist_node, critic_node]:
            result = node(state)
            state.update({k: v for k, v in result.items() if k != "trace"})
            state["trace"].extend(result.get("trace", []))
        route = revision_router(state)
        if route == "increment_retry_node":
            result = increment_retry_node(state)
            state.update({k: v for k, v in result.items() if k != "trace"})
            state["trace"].extend(result.get("trace", []))
            continue
        result = final_response_node(state) if route == "final_response_node" else safe_fallback_final_response_node(state)
        state.update({k: v for k, v in result.items() if k != "trace"})
        state["trace"].extend(result.get("trace", []))
        save_result = save_trace_node(state)
        state["trace"].extend(save_result.get("trace", []))
        break
    return state


def build_workflow():
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return None

    graph = StateGraph(DriverCopilotState)
    graph.add_node("extract_context_node", extract_context_node)
    graph.add_node("load_driver_profile_node", load_driver_profile_node)
    graph.add_node("load_support_tickets_node", load_support_tickets_node)
    graph.add_node("load_incentives_node", load_incentives_node)
    graph.add_node("strategist_node", strategist_node)
    graph.add_node("critic_node", critic_node)
    graph.add_node("increment_retry_node", increment_retry_node)
    graph.add_node("final_response_node", final_response_node)
    graph.add_node("safe_fallback_final_response_node", safe_fallback_final_response_node)
    graph.add_node("save_trace_node", save_trace_node)

    graph.add_edge(START, "extract_context_node")
    graph.add_edge("extract_context_node", "load_driver_profile_node")
    graph.add_edge("load_driver_profile_node", "load_support_tickets_node")
    graph.add_edge("load_support_tickets_node", "load_incentives_node")
    graph.add_edge("load_incentives_node", "strategist_node")
    graph.add_edge("strategist_node", "critic_node")
    graph.add_conditional_edges(
        "critic_node",
        revision_router,
        {
            "final_response_node": "final_response_node",
            "increment_retry_node": "increment_retry_node",
            "safe_fallback_final_response_node": "safe_fallback_final_response_node",
        },
    )
    graph.add_edge("increment_retry_node", "strategist_node")
    graph.add_edge("final_response_node", "save_trace_node")
    graph.add_edge("safe_fallback_final_response_node", "save_trace_node")
    graph.add_edge("save_trace_node", END)
    return graph.compile()


def run_copilot(query: str, conversation_memory: dict | None = None, max_retries: int | None = None) -> DriverCopilotState:
    initial_state: DriverCopilotState = {
        "user_query": query,
        "driver_id": None,
        "driver_name": None,
        "driver_profile": None,
        "support_tickets": [],
        "issue_type": None,
        "risk_level": None,
        "incentive_options": None,
        "retrieved_policy_chunks": [],
        "strategist_plan": None,
        "critic_verdict": None,
        "final_answer": None,
        "retry_count": 0,
        "max_retries": max_retries if max_retries is not None else int(os.getenv("MAX_CORRECTION_ATTEMPTS", "2")),
        "conversation_memory": conversation_memory or {},
        "trace": [],
    }
    workflow = build_workflow()
    if workflow is None:
        return _fallback_run(initial_state)
    return workflow.invoke(initial_state)
