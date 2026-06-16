# Technical Design

The system uses a LangGraph workflow because the assignment is a conditional, stateful agent process: context extraction, tool retrieval, strategy generation, policy validation, retry, and finalization. A sequential fallback is included so offline tests and demos can still run if LangGraph is not installed.

The Strategist/Critic split implements an Actor/Validator pattern. The Strategist optimizes for retention using profile data, support tickets, and incentive options. The Compliance Critic retrieves policy evidence and runs deterministic validation before anything reaches the manager.

OpenRouter is used only for chat reasoning through `llm/llm_client.py`. API keys, base URL, and model ID are environment-configured. `llm/json_utils.py` strips Markdown fences, extracts JSON, validates with Pydantic, and performs one repair retry. No secrets or model IDs are hardcoded.

Policy RAG uses local `sentence-transformers` embeddings and raw ChromaDB. `rag/ingest_policy.py` extracts the PDF, chunks it with metadata, and persists chunks. `rag/retriever.py` returns evidence chunks to the Critic. RAG is used for citations and context, not as the source of truth for hard caps.

Verified hard rules from the policy PDF are encoded in `tools/policy_rules.py`. `tools/policy_validator.py` deterministically rejects over-cap compensation, returns `needs_review` for unknown monetary actions, and allows harmless non-monetary actions such as `manager_message`, `future_quest`, `monitor_driver`, and `follow_up_call`. This prevents hallucinated approvals and avoids false manual-review routing for safe actions.

Memory is persisted as JSON by `state/memory.py`, keyed by `--session-id`. It stores the last driver, issue type, and plan so follow-up questions can resolve pronouns such as "her" to the prior driver in CLI or Streamlit sessions.

Retry semantics are explicit: `retry_count` starts at 0, increments only in `increment_retry_node`, and the router only reads state. `max_retries=2` allows the initial plan plus two revisions. `needs_review` routes directly to fallback because rewriting cannot fix unclear policy.

Self-correction is proven deterministically in `evaluation/seeded_invalid_plan.json` and `evaluation/run_eval.py`: a 50 GBP short-fare credit is rejected, revised to the verified cap, and approved. This guarantees `outputs/evaluation_trace.json` shows rejected -> revised -> approved even if the live LLM generates a compliant plan on the first attempt.

For the 48-hour implementation, the graph calls local Python tool functions directly for reliability and simplicity. The MCP server exposes the same tool layer as an MCP-compatible interface, making the system MCP-ready without duplicating business logic. In a production deployment, the agent runtime could route tool calls through MCP instead of direct imports.

Production-minded choices include a centralized LLM client, environment configuration, structured Pydantic outputs, tool failure handling, bounded retries, policy-grounded validation, deterministic cap checks, non-monetary action allowlisting, JSON trace logging, offline deterministic tests, swappable LLM and embedding providers, and an MCP-ready exposure layer.

To scale from the demo to thousands of drivers, profile/ticket reads should move from local files to indexed services, policy chunks should be versioned by market and effective date, traces should go to durable storage, and policy rules should be reviewed through a compliance-owned change process.
