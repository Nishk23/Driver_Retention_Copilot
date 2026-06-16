import operator
from typing import Annotated, Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field


IssueType = Literal[
    "airport_short_fare",
    "bonus_confusion",
    "technical_issue",
    "low_earnings",
    "support_delay",
    "unknown",
]


class RetentionAction(BaseModel):
    action_type: str
    amount: float | None = None
    currency: str | None = None
    description: str | None = None
    reason: str | None = None
    incentive_id: str | None = None


class RetentionPlan(BaseModel):
    risk_level: str = "unknown"
    issue_type: IssueType = "unknown"
    reasoning: str
    evidence_summary: list[str] = Field(default_factory=list)
    proposed_actions: list[RetentionAction] = Field(default_factory=list)
    manager_message: str
    assumptions: list[str] = Field(default_factory=list)


class PolicyEvidence(BaseModel):
    page: int | None = None
    chunk_id: str | None = None
    text: str
    score: float | None = None


class CriticVerdict(BaseModel):
    status: Literal["approved", "rejected", "needs_review"]
    violations: list[dict] = Field(default_factory=list)
    required_fixes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    policy_evidence: list[PolicyEvidence] = Field(default_factory=list)
    explanation: str


class TraceEntry(BaseModel):
    step: str
    data: dict[str, Any] = Field(default_factory=dict)


class EvaluationTrace(BaseModel):
    run_id: str
    trace: list[dict] = Field(default_factory=list)
    final_answer: str | None = None


class DriverCopilotState(TypedDict, total=False):
    user_query: str
    driver_id: Optional[str]
    driver_name: Optional[str]
    driver_profile: Optional[dict]
    support_tickets: list[dict]
    issue_type: Optional[str]
    risk_level: Optional[str]
    incentive_options: Optional[dict]
    retrieved_policy_chunks: list[dict]
    strategist_plan: Optional[dict]
    critic_verdict: Optional[dict]
    final_answer: Optional[str]
    retry_count: int
    max_retries: int
    conversation_memory: dict
    trace: Annotated[list[dict], operator.add]
