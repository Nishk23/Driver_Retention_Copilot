# Technical Design

## Architecture

- The system is implemented as a LangGraph workflow with explicit state passed between nodes.
- The main workflow stages are:
  - Extract driver, issue type, and conversation context.
  - Retrieve driver profile and support ticket evidence.
  - Load eligible incentives from the incentive tool.
  - Generate a retention plan with the Strategist.
  - Retrieve policy evidence and validate the plan with the Compliance Critic.
  - Retry with Critic feedback when a plan violates policy.
  - Produce a final manager-facing recommendation.
- A sequential fallback runner is included so the workflow remains usable in lightweight environments.

## Agent Roles

- **Strategist**
  - Uses driver profile, support tickets, issue type, and incentive options.
  - Produces a structured retention plan with risk level, reasoning, evidence, proposed actions, and manager message.
  - Revises plans after policy rejection by applying the Critic's feedback.

- **Compliance Critic**
  - Retrieves relevant policy chunks before validation.
  - Runs deterministic policy checks before a recommendation is finalized.
  - Returns `approved`, `rejected`, or `needs_review` with violations, required fixes, warnings, and policy evidence.

## LLM Integration

- OpenRouter is used only for chat reasoning through `llm/llm_client.py`.
- API key, base URL, and model ID are read from environment variables.
- `llm/json_utils.py` handles:
  - Markdown fence stripping.
  - JSON extraction.
  - Pydantic validation.
  - One repair retry for malformed model output.
- No secrets or model IDs are hardcoded.

## RAG Strategy

- Policy RAG is implemented in `rag/`.
- `rag/ingest_policy.py` extracts the policy PDF, chunks it with metadata, and persists chunks.
- `rag/retriever.py` retrieves relevant evidence for the Compliance Critic.
- The semantic retrieval path uses local `sentence-transformers` embeddings and ChromaDB.
- A deterministic keyword fallback is available for faster demos and environments without local embedding dependencies.
- RAG provides policy context and citations; hard approval limits are enforced separately by deterministic rules.

## Policy Validation

- Verified hard rules are encoded in `tools/policy_rules.py`.
- `tools/policy_validator.py` enforces caps and guardrails, including:
  - Gold airport short-fare cap: 25 GBP.
  - Silver/Bronze airport short-fare cap: 15 GBP.
  - Technical/GPS glitch cap: 10 GBP.
  - Global monthly compensation cap.
  - Manual review for unknown monetary actions.
- Safe non-monetary actions are allowlisted, including:
  - `manager_message`
  - `future_quest`
  - `monitor_driver`
  - `follow_up_call`
- This keeps LLM-generated plans policy-bound and prevents unsupported monetary approvals.

## State And Memory

- Runtime state is represented with Pydantic schemas in `state/schemas.py`.
- Session memory is persisted as JSON by `state/memory.py`.
- Memory is keyed by `--session-id` in CLI and Streamlit.
- Stored memory includes:
  - Last driver ID.
  - Last driver name.
  - Last issue type.
  - Last strategist plan.
- Follow-up questions can resolve references such as "her", "his", or "their" back to the prior driver.

## Self-Correction Loop

- Retry behavior is explicit and bounded.
- `retry_count` starts at `0` and increments only in `increment_retry_node`.
- `max_retries=2` allows the initial plan plus two revisions.
- Rejected plans route back to the Strategist with Critic feedback.
- `needs_review` routes directly to a safe fallback instead of forcing an unsafe rewrite.
- `evaluation/run_eval.py` proves the loop by:
  - Starting with a seeded 50 GBP short-fare credit.
  - Having the Critic reject it against the 25 GBP cap.
  - Revising the action to the compliant cap.
  - Producing an approved second verdict.
- The exported trace is saved to `outputs/evaluation_trace.json`.

## Tooling And MCP Readiness

- Business tools live in `tools/`:
  - Driver profile lookup.
  - Support ticket retrieval.
  - Incentive calculation.
  - Policy retrieval.
  - Policy validation.
- `mcp_server/server.py` exposes the same tool layer through FastMCP when available.
- The graph calls the local Python tool functions directly while keeping the tool boundary compatible with MCP-style deployment.

## Reliability And Operations

- Structured Pydantic outputs reduce malformed agent responses.
- Deterministic validation protects against hallucinated or over-cap actions.
- Bounded retries prevent infinite correction loops.
- Missing driver profiles route to manual review instead of compensation.
- Unknown monetary actions route to manual review.
- Offline tests cover policy validation, self-correction, and workflow regressions.
- JSON traces provide auditability for recommendations and policy decisions.

## Scaling Path

- Move driver profiles and tickets from local files to indexed services.
- Store conversation memory in a database-backed checkpointer.
- Version policy chunks by market, policy document, and effective date.
- Send traces to durable storage for audit and monitoring.
- Add latency, retry, and rate-limit observability around LLM calls.
- Manage policy rules through a compliance-owned review process.
