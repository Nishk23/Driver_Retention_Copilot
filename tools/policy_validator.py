import re

from tools.policy_rules import MONETARY_ACTION_TYPES, NON_MONETARY_ALLOWLIST, POLICY_CAPS


def _evidence(policy_chunks: list[dict]) -> list[dict]:
    return [
        {
            "page": chunk.get("page"),
            "chunk_id": chunk.get("chunk_id") or chunk.get("id"),
            "text": chunk.get("text", ""),
            "score": chunk.get("score"),
        }
        for chunk in (policy_chunks or [])[:5]
    ]


def _is_monetary(action: dict) -> bool:
    action_type = action.get("action_type", "")
    return action_type in MONETARY_ACTION_TYPES or action.get("amount") is not None


def _short_fare_cap(plan: dict, action: dict) -> float:
    caps = POLICY_CAPS["short_fare_credit"]
    profile = plan.get("driver_profile") or {}
    tier = profile.get("loyalty_tier") or plan.get("driver_tier")
    return caps.get("tier_caps", {}).get(tier, caps["max_amount"])


def _available_incentive_ids(plan: dict) -> set[str]:
    incentives = (plan.get("incentive_options") or {}).get("incentives") or []
    return {incentive.get("id") for incentive in incentives if incentive.get("id")}


def _gbp_amount(action: dict) -> float:
    if action.get("amount") is None:
        return 0.0
    currency = action.get("currency") or "GBP"
    if currency != "GBP":
        return 0.0
    return float(action.get("amount") or 0.0)


def _evidence_text(plan: dict) -> str:
    parts = [plan.get("reasoning", ""), plan.get("user_query", "")]
    parts.extend(plan.get("evidence_summary") or [])
    parts.extend(ticket.get("message", "") for ticket in plan.get("support_tickets") or [])
    return " ".join(str(part) for part in parts if part)


def _airport_short_fare_eligibility(plan: dict) -> tuple[bool, list[str]]:
    text = _evidence_text(plan).lower()
    warnings: list[str] = []

    wait_values = [int(value) for value in re.findall(r"(\d+)\s*(?:min|mins|minute|minutes)", text)]
    if wait_values and max(wait_values) <= 90:
        return False, ["Airport short-fare credit requires wait time greater than 90 minutes."]
    if not wait_values:
        warnings.append("No explicit airport wait time found for short-fare eligibility.")

    distances = [
        float(value)
        for value in re.findall(r"(\d+(?:\.\d+)?)\s*(?:km|kilometre|kilometer|mile|miles)", text)
    ]
    if distances and min(distances) >= 3:
        return False, ["Airport short-fare credit requires trip distance below 3km."]
    if not distances and "short fare" not in text and "short-fare" not in text:
        warnings.append("No explicit short trip distance found for short-fare eligibility.")

    return True, warnings


def validate_plan_against_policy(plan: dict, policy_chunks: list[dict]) -> dict:
    violations: list[dict] = []
    warnings: list[str] = []
    required_fixes: list[str] = []
    unknown_monetary = False
    available_ids = _available_incentive_ids(plan)

    actions = plan.get("proposed_actions") or []
    if not actions:
        return {
            "status": "needs_review",
            "violations": [],
            "warnings": ["Plan contains no proposed actions."],
            "required_fixes": ["Add at least one concrete action or route to manual review."],
            "policy_evidence": _evidence(policy_chunks),
            "explanation": "A plan with no actions cannot be approved.",
        }

    total_gbp = sum(_gbp_amount(action) for action in actions if _is_monetary(action))
    monthly_cap = POLICY_CAPS["global_monthly"]["max_amount"]
    if total_gbp > monthly_cap:
        violations.append(
            {
                "action": "retention_package",
                "proposed_amount": total_gbp,
                "allowed_amount": monthly_cap,
                "reason": "Total automated retention package exceeds global monthly cap.",
            }
        )
        required_fixes.append(f"Reduce total GBP compensation to {monthly_cap:.0f} GBP or below.")

    for action in actions:
        action_type = action.get("action_type")
        amount = action.get("amount")
        incentive_id = action.get("incentive_id")

        if incentive_id and available_ids and incentive_id not in available_ids:
            unknown_monetary = True
            warnings.append(f"Incentive ID is not available for this driver: {incentive_id}.")
            required_fixes.append("Use only incentive IDs returned by the Incentive Service or remove the incentive_id.")

        if action_type == "short_fare_credit":
            allowed = _short_fare_cap(plan, action)
            eligible, eligibility_notes = _airport_short_fare_eligibility(plan)
            if not eligible:
                violations.append(
                    {
                        "action": action_type,
                        "reason": "Airport short-fare eligibility evidence does not satisfy policy conditions.",
                    }
                )
                required_fixes.extend(eligibility_notes)
            else:
                warnings.extend(eligibility_notes)
            if amount is None:
                unknown_monetary = True
                warnings.append("short_fare_credit is missing amount.")
            elif float(amount) > allowed:
                violations.append(
                    {
                        "action": action_type,
                        "proposed_amount": float(amount),
                        "allowed_amount": allowed,
                        "reason": "Proposed amount exceeds Airport Short Fare compensation cap.",
                    }
                )
                required_fixes.append(f"Reduce short_fare_credit to {allowed:.0f} GBP or below.")
            continue

        if action_type == "technical_glitch_credit":
            allowed = POLICY_CAPS["technical_glitch_credit"]["max_amount"]
            if amount is None:
                unknown_monetary = True
                warnings.append("technical_glitch_credit is missing amount.")
            elif float(amount) > allowed:
                violations.append(
                    {
                        "action": action_type,
                        "proposed_amount": float(amount),
                        "allowed_amount": allowed,
                        "reason": "Proposed amount exceeds Technical/GPS glitch compensation cap.",
                    }
                )
                required_fixes.append(f"Reduce technical_glitch_credit to {allowed:.0f} GBP or below.")
            continue

        if action_type in NON_MONETARY_ALLOWLIST:
            continue

        if _is_monetary(action):
            unknown_monetary = True
            warnings.append(f"Unknown monetary action requires manual review: {action_type}.")
        else:
            warnings.append(f"Unknown non-monetary action treated as warning: {action_type}.")

    if violations:
        status = "rejected"
        explanation = "One or more actions violate deterministic policy caps."
    elif unknown_monetary:
        status = "needs_review"
        explanation = "Unknown monetary actions cannot be approved automatically."
        if not required_fixes:
            required_fixes.append("Route unknown monetary action to manual review or map it to a known policy rule.")
    else:
        status = "approved"
        explanation = (
            "All monetary actions are within deterministic policy caps, and non-monetary actions are allowlisted or harmless."
        )

    return {
        "status": status,
        "violations": violations,
        "warnings": warnings,
        "required_fixes": required_fixes,
        "policy_evidence": _evidence(policy_chunks),
        "explanation": explanation,
    }
