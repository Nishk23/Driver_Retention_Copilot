# Technical Design

## Overview

- The system is a LangGraph-based Driver Retention Copilot with explicit state passed through each workflow node.
- Flow: manager query -> context extraction -> driver/ticket retrieval -> incentive lookup -> Strategist plan -> policy retrieval -> Compliance Critic validation -> retry or final response.
- The Strategist proposes a retention plan from driver profile, support tickets, issue type, and available incentives.
- The Compliance Critic validates the plan before it reaches the manager and returns `approved`, `rejected`, or `needs_review`.

## RAG And Tools

- Structured data comes from `driver_profiles.json`, `support_tickets.csv`, and `incentive_service_mock.py` through the `tools/` layer.
- Policy RAG lives in `rag/`: `ingest_policy.py` extracts section-level chunks with page metadata; `retriever.py` returns focused policy evidence to the Critic.
- Semantic retrieval uses local `sentence-transformers` embeddings with ChromaDB; keyword fallback keeps demos/tests reliable when embeddings are unavailable.
- `mcp_server/server.py` exposes the same tool layer through FastMCP when installed, while the graph calls local Python tools directly.

## Safety And Grounding

- Agent prompts in `agents/prompts.py` require evidence-only reasoning: no invented driver facts, policies, incentive IDs, ticket details, compensation amounts, cities, or tiers.
- The Strategist can recommend only incentives present in `incentive_options`; insufficient evidence routes to escalation, follow-up, monitoring, or manual review.
- `tools/policy_validator.py` deterministically enforces airport short-fare caps, technical glitch caps, the global monthly cap, incentive-ID validity, eligibility evidence, and manual review for unknown monetary actions.
- Pydantic schemas and JSON repair in `llm/json_utils.py` keep model output structured; API keys and model IDs are environment-configured.

## State, Memory, And Self-Correction

- Runtime state is typed in `state/schemas.py` and includes driver context, retrieved evidence, incentive options, proposed plan, Critic verdict, retry count, and trace entries.
- Session memory is persisted by `state/memory.py` under `outputs/memory/`, keyed by `--session-id`, and stores the last driver, issue type, and plan for follow-up questions.
- Rejected plans route back to the Strategist with Critic feedback; `max_retries=2` bounds the correction loop.
- `needs_review` routes to a safe fallback instead of forcing an unsafe rewrite.
- `evaluation/run_eval.py` exports `outputs/evaluation_trace.json`, showing a seeded 50 GBP short-fare credit rejected against the 25 GBP cap, revised, and approved.

## Reliability And Scaling

- Offline tests cover policy validation, self-correction, and workflow regressions.
- JSON traces provide auditability for recommendations and validation decisions.
- For scale, local files should move to indexed services, memory to a database-backed checkpointer, policy chunks to versioned storage, and traces to durable observability infrastructure.
