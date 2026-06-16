import datetime
from typing import List, Dict, Union


class IncentiveService:
    def __init__(self):
        self._all_incentives = [
            # --- AIRPORT RECOVERY ---
            {"id": "INC-001", "type": "CREDIT", "category": "Airport", "name": "Standard Airport Short Fare Recovery",
             "value": 25.0, "currency": "GBP", "min_tier": "Bronze"},
            {"id": "INC-002", "type": "CREDIT", "category": "Airport", "name": "Premium Airport Short Fare Recovery",
             "value": 50.0, "currency": "GBP", "min_tier": "Gold"},

            # --- TECHNICAL & GPS RECOVERY ---
            {"id": "INC-003", "type": "CREDIT", "category": "Technical", "name": "Geofence/GPS Glitch Credit",
             "value": 10.0, "currency": "GBP", "min_tier": "Bronze"},
            {"id": "INC-004", "type": "CREDIT", "category": "Technical", "name": "Priority Technical Support Access",
             "value": 0.0, "currency": "GBP", "min_tier": "Silver",
             "description": "Moves driver to the front of the dev-ops fix queue."},

            # --- NEW STARTER & TENURE ---
            {"id": "INC-005", "type": "CREDIT", "category": "Tenure", "name": "New Starter Retention Bonus",
             "value": 30.0, "currency": "GBP", "min_tier": "Bronze", "max_tenure_months": 3},
            {"id": "INC-006", "type": "DISCOUNT", "category": "Commission", "name": "First Month Commission Shield",
             "value": 50.0, "currency": "PERCENT", "min_tier": "Bronze", "max_tenure_months": 1},

            # --- LOYALTY & CHURN PREVENTION ---
            {"id": "INC-007", "type": "CREDIT", "category": "Churn", "name": "High-Value Partner Goodwill",
             "value": 75.0, "currency": "GBP", "min_tier": "Gold"},
            {"id": "D-001", "type": "DISCOUNT", "category": "Commission", "name": "Commission-Free Afternoon",
             "value": 100.0, "currency": "PERCENT", "min_tier": "Silver",
             "description": "0% commission for the next 4 hours"},

            # --- FUTURE QUESTS (Engagement) ---
            {"id": "Q-101", "type": "QUEST", "category": "Growth", "name": "London Morning Rush Hero", "value": 30.0,
             "currency": "GBP", "min_tier": "Bronze", "requirement": "Complete 5 trips tomorrow 07:00-10:00"},
            {"id": "Q-102", "type": "QUEST", "category": "Growth", "name": "London Mid-Week Sustainability Quest",
             "value": 45.0, "currency": "GBP", "min_tier": "Silver",
             "requirement": "Complete 10 trips on Wednesday/Thursday"},
            {"id": "Q-103", "type": "QUEST", "category": "Engagement", "name": "Airport Fast-Track Voucher",
             "value": 0.0, "currency": "GBP", "min_tier": "Gold",
             "description": "One-time skip to the front of the airport queue tomorrow."}
        ]

    def get_available_incentives(self, city: str, loyalty_tier: str, tenure_months: int) -> Dict[str, List[Dict]]:
        if city.lower() != "london":
            return {"error": f"Incentive Engine currently only calibrated for London."}

        tier_rank = {"Bronze": 1, "Silver": 2, "Gold": 3}
        driver_rank = tier_rank.get(loyalty_tier, 1)

        eligible = [
            inc for inc in self._all_incentives
            if tier_rank.get(inc.get("min_tier", "Bronze"), 1) <= driver_rank
               and tenure_months <= inc.get("max_tenure_months", 999)
        ]

        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "city": city,
            "driver_tier": loyalty_tier,
            "tenure_months": tenure_months,
            "incentives": eligible
        }
