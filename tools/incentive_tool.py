import importlib.util
from pathlib import Path

from tools.driver_profile_tool import get_driver_profile


SERVICE_PATH = Path(__file__).resolve().parents[1] / "data" / "incentive_service_mock.py"


def _load_service_class():
    spec = importlib.util.spec_from_file_location("incentive_service_mock", SERVICE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load incentive_service_mock.py.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "IncentiveService")


def _service():
    return _load_service_class()()


def _filter_by_issue(incentives: list[dict], issue_type: str | None) -> list[dict]:
    if not issue_type:
        return incentives
    category_map = {
        "airport_short_fare": {"Airport", "Growth", "Engagement", "Churn"},
        "technical_issue": {"Technical", "Churn"},
        "bonus_confusion": {"Growth", "Commission", "Churn"},
        "low_earnings": {"Growth", "Commission", "Churn"},
        "support_delay": {"Technical", "Churn"},
    }
    allowed = category_map.get(issue_type, set())
    if not allowed:
        return incentives
    return [inc for inc in incentives if inc.get("category") in allowed]


def get_available_incentives(driver_id: str, issue_type: str | None = None) -> dict:
    profile = get_driver_profile(driver_id)
    if profile.get("error"):
        return profile
    try:
        result = _service().get_available_incentives(
            city=profile["city"],
            loyalty_tier=profile["loyalty_tier"],
            tenure_months=int(profile["tenure_months"]),
        )
        if "incentives" in result:
            result["incentives"] = _filter_by_issue(result["incentives"], issue_type)
        return result
    except Exception as exc:
        return {"error": f"Incentive service failure: {exc}"}


def calculate_retention_options(driver_id: str, issue_type: str, driver_profile: dict) -> dict:
    options = get_available_incentives(driver_id, issue_type)
    options["issue_type"] = issue_type
    options["driver_profile_summary"] = {
        "driver_id": driver_profile.get("driver_id"),
        "tier": driver_profile.get("loyalty_tier"),
        "tenure_months": driver_profile.get("tenure_months"),
    }
    return options
