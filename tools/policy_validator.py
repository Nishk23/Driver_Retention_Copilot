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


def validate_plan_against_policy(plan: dict, policy_chunks: list[dict]) -> dict:
    violations: list[dict] = []
    warnings: list[str] = []
    required_fixes: list[str] = []
    unknown_monetary = False

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

    for action in actions:
        action_type = action.get("action_type")
        amount = action.get("amount")

        if action_type == "short_fare_credit":
            allowed = _short_fare_cap(plan, action)
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
