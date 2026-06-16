import json
import os
import sys
from pathlib import Path
from contextlib import contextmanager

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graph.workflow import run_copilot
from state.memory import load_memory, save_memory, update_memory


DEFAULT_QUERY = (
    "Driver Maria D-456 just called. She waited in the airport queue for two hours only to be given "
    "a 1.5km trip. She's furious as this has happened multiple times. How do we handle this?"
)


st.set_page_config(page_title="Driver Retention Copilot", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
    :root {
      --ink: #202331;
      --muted: #667085;
      --line: #E3E7EE;
      --panel: #FFFFFF;
      --soft: #F6F8FB;
      --brand: #E91D2D;
      --ok: #0E7A4F;
      --warn: #B54708;
    }
    .block-container { padding-top: 2.25rem; max-width: 1280px; }
    [data-testid="stSidebar"] { background: #F3F5F8; border-right: 1px solid var(--line); }
    h1, h2, h3 { color: var(--ink); letter-spacing: 0; }
    h1 { font-size: 2.2rem; margin-bottom: .25rem; }
    .subtle { color: var(--muted); font-size: .95rem; }
    .topline { height: 4px; background: var(--brand); margin: -2.25rem -4rem 1.8rem -4rem; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px 18px 16px;
      box-shadow: 0 1px 2px rgba(16, 24, 40, .04);
      margin-bottom: 14px;
    }
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 18px 0 8px;
    }
    .metric-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 16px;
      min-height: 88px;
    }
    .metric-label {
      color: var(--muted);
      font-size: .78rem;
      text-transform: uppercase;
      font-weight: 700;
      margin-bottom: 8px;
    }
    .metric-value { color: var(--ink); font-size: 1.25rem; font-weight: 750; }
    .badge {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 5px 10px;
      font-size: .8rem;
      font-weight: 750;
      border: 1px solid transparent;
    }
    .badge-ok { color: var(--ok); background: #ECFDF3; border-color: #ABEFC6; }
    .badge-warn { color: var(--warn); background: #FFFAEB; border-color: #FEDF89; }
    .badge-risk { color: #B42318; background: #FEF3F2; border-color: #FECDCA; }
    .action-item {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 13px 14px;
      margin-bottom: 10px;
      background: #fff;
    }
    .action-title { font-weight: 750; color: var(--ink); margin-bottom: 4px; }
    .action-meta { color: var(--muted); font-size: .88rem; }
    .callout {
      border-left: 4px solid var(--brand);
      background: #FFF7F7;
      padding: 12px 14px;
      border-radius: 6px;
      color: var(--ink);
      margin-top: 8px;
    }
    .section-title {
      font-size: 1.05rem;
      font-weight: 800;
      color: var(--ink);
      margin: 0 0 12px;
    }
    .stDataFrame { border: 1px solid var(--line); border-radius: 8px; }
    div[data-testid="stTextArea"] textarea {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      font-size: .96rem;
    }
    div[data-testid="stButton"] button {
      border-radius: 8px;
      height: 42px;
      font-weight: 750;
      border: 0;
      background: var(--brand);
    }
    @media (max-width: 900px) {
      .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .topline { margin-left: -1rem; margin-right: -1rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _display(value, fallback="Not available"):
    if value is None or value == "":
        return fallback
    return value


def _money(action: dict) -> str:
    amount = action.get("amount")
    if amount is None:
        return "Non-monetary"
    currency = action.get("currency") or "GBP"
    try:
        return f"{float(amount):.0f} {currency}"
    except (TypeError, ValueError):
        return f"{amount} {currency}"


def _status_badge(status: str) -> str:
    if status == "approved":
        return '<span class="badge badge-ok">Approved</span>'
    if status == "rejected":
        return '<span class="badge badge-risk">Rejected</span>'
    return '<span class="badge badge-warn">Needs review</span>'


def _risk_badge(risk: str) -> str:
    if risk == "high":
        return '<span class="badge badge-risk">High risk</span>'
    if risk == "medium":
        return '<span class="badge badge-warn">Medium risk</span>'
    return '<span class="badge badge-ok">Low risk</span>'


def _trace_has_rejection(trace: list[dict]) -> bool:
    return any(
        entry.get("step", "").startswith("critic_verdict")
        and entry.get("data", {}).get("status") == "rejected"
        for entry in trace
    )


def _action_rows(plan: dict) -> list[dict]:
    rows = []
    for action in plan.get("proposed_actions") or []:
        rows.append(
            {
                "Action": action.get("action_type", "unknown"),
                "Value": _money(action),
                "Incentive": action.get("incentive_id") or "-",
                "Rationale": action.get("reason") or action.get("description") or "-",
            }
        )
    return rows


def _ticket_rows(tickets: list[dict]) -> list[dict]:
    rows = []
    for ticket in tickets or []:
        rows.append(
            {
                "Ticket": ticket.get("ticket_id"),
                "Category": ticket.get("category"),
                "Status": ticket.get("status"),
                "Timestamp": ticket.get("timestamp"),
                "Message": ticket.get("message"),
            }
        )
    return rows


def _table(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows).fillna("-").astype(str)


def _render_metric(label: str, value: str) -> str:
    return f"""
    <div class="metric-card">
      <div class="metric-label">{label}</div>
      <div class="metric-value">{value}</div>
    </div>
    """


def _render_action_cards(plan: dict) -> None:
    actions = plan.get("proposed_actions") or []
    if not actions:
        st.info("No proposed actions were generated.")
        return
    for action in actions:
        title = action.get("action_type", "unknown").replace("_", " ").title()
        value = _money(action)
        detail = action.get("description") or action.get("reason") or "No rationale provided."
        incentive = action.get("incentive_id")
        st.markdown(
            f"""
            <div class="action-item">
              <div class="action-title">{title}</div>
              <div class="action-meta">{value}{f" · {incentive}" if incentive else ""}</div>
              <div>{detail}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


@contextmanager
def _llm_mode(enabled: bool):
    if enabled:
        yield
        return

    saved = {
        "OPENROUTER_API_KEY": os.environ.get("OPENROUTER_API_KEY"),
        "MODEL_NAME": os.environ.get("MODEL_NAME"),
    }
    os.environ.pop("OPENROUTER_API_KEY", None)
    os.environ.pop("MODEL_NAME", None)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _render_result(result: dict) -> None:
    profile = result.get("driver_profile") or {}
    plan = result.get("strategist_plan") or {}
    verdict = result.get("critic_verdict") or {}
    trace = result.get("trace") or []
    tickets = result.get("support_tickets") or []

    status = verdict.get("status", "needs_review")
    risk = plan.get("risk_level") or result.get("risk_level") or "unknown"
    driver_name = _display(profile.get("name"), "Unknown driver")
    driver_id = _display(profile.get("driver_id") or result.get("driver_id"), "Unknown ID")

    metric_cols = st.columns(4)
    metric_values = [
        ("Driver", f"{driver_name}<br><span class='subtle'>{driver_id}</span>"),
        ("Tier", _display(profile.get("loyalty_tier"))),
        ("Risk", _risk_badge(risk)),
        ("Compliance", _status_badge(status)),
    ]
    for col, (label, value) in zip(metric_cols, metric_values):
        with col:
            st.markdown(_render_metric(label, value), unsafe_allow_html=True)

    overview_tab, evidence_tab, compliance_tab, trace_tab = st.tabs(
        ["Recommendation", "Evidence", "Compliance", "Trace"]
    )

    with overview_tab:
        left, right = st.columns([1.35, 1], gap="large")
        with left:
            st.markdown('<div class="section-title">Recommended actions</div>', unsafe_allow_html=True)
            _render_action_cards(plan)
            manager_message = plan.get("manager_message")
            if manager_message:
                st.markdown('<div class="section-title">Manager message</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="callout">{manager_message}</div>', unsafe_allow_html=True)
        with right:
            st.markdown('<div class="section-title">Driver context</div>', unsafe_allow_html=True)
            context = {
                "City": profile.get("city"),
                "Tenure": f"{profile.get('tenure_months')} months" if profile.get("tenure_months") is not None else None,
                "Lifetime value": f"€{profile.get('lifetime_value_euro'):,}" if profile.get("lifetime_value_euro") else None,
                "Status": profile.get("current_status"),
                "Sentiment": profile.get("recent_sentiment"),
                "Short fares 30d": profile.get("airport_short_fare_count_30d"),
            }
            st.dataframe(
                _table(
                    [{"Field": key, "Value": _display(value)} for key, value in context.items()]
                ),
                hide_index=True,
                width="stretch",
            )

            st.markdown('<div class="section-title">Decision</div>', unsafe_allow_html=True)
            if status == "approved":
                st.success("Final recommendation is approved by the Compliance Critic.")
            else:
                st.warning("This case needs manual review before action.")

    with evidence_tab:
        st.markdown('<div class="section-title">Support tickets</div>', unsafe_allow_html=True)
        ticket_rows = _ticket_rows(tickets)
        if ticket_rows:
            st.dataframe(_table(ticket_rows), hide_index=True, width="stretch", height=280)
        else:
            st.info("No matching support tickets found.")

        st.markdown('<div class="section-title">Evidence summary</div>', unsafe_allow_html=True)
        for item in plan.get("evidence_summary") or []:
            st.markdown(f"- {item}")

    with compliance_tab:
        col_a, col_b = st.columns([1, 1], gap="large")
        with col_a:
            st.markdown('<div class="section-title">Validator result</div>', unsafe_allow_html=True)
            st.markdown(_status_badge(status), unsafe_allow_html=True)
            st.write(verdict.get("explanation", "No explanation available."))
            if _trace_has_rejection(trace):
                st.info("An earlier plan was rejected and then corrected before final approval.")
            for fix in verdict.get("required_fixes") or []:
                st.markdown(f"- Required fix: {fix}")
            for warning in verdict.get("warnings") or []:
                st.markdown(f"- Warning: {warning}")
        with col_b:
            st.markdown('<div class="section-title">Policy evidence</div>', unsafe_allow_html=True)
            evidence = verdict.get("policy_evidence") or []
            if evidence:
                for item in evidence:
                    page = item.get("page")
                    text = item.get("text", "")
                    st.markdown(f"**Page {page or '-'}**")
                    st.caption(text[:650])
            else:
                st.info("No policy evidence attached.")

        with st.expander("Action table"):
            rows = _action_rows(plan)
            if rows:
                st.dataframe(_table(rows), hide_index=True, width="stretch")

    with trace_tab:
        steps = [
            {
                "Step": entry.get("step"),
                "Status": entry.get("data", {}).get("status", ""),
                "Details": json.dumps(entry.get("data", {}), ensure_ascii=False)[:220],
            }
            for entry in trace
        ]
        st.dataframe(_table(steps), hide_index=True, width="stretch")
        with st.expander("Raw final answer"):
            st.text(result.get("final_answer", "No final answer generated."))
        with st.expander("Raw JSON payload"):
            st.code(json.dumps(result, indent=2, ensure_ascii=False), language="json")


def _reset_query() -> None:
    st.session_state.query = DEFAULT_QUERY
    st.session_state.result = None


with st.sidebar:
    st.markdown("### Session")
    session_id = st.text_input("Session ID", value="streamlit-demo")
    st.markdown("### Run")
    use_memory = st.toggle("Persist memory", value=True)
    use_live_llm = st.toggle("Use live LLM", value=False)
    st.caption("Memory stores the last driver and issue for follow-up questions.")

st.markdown('<div class="topline"></div>', unsafe_allow_html=True)
st.title("Driver Retention Copilot")
st.markdown(
    '<div class="subtle">Policy-aware retention planning for Driver Relationship Managers.</div>',
    unsafe_allow_html=True,
)

if "query" not in st.session_state:
    st.session_state.query = DEFAULT_QUERY
if "result" not in st.session_state:
    st.session_state.result = None

with st.container():
    query = st.text_area("Manager question", key="query", height=118)
    run_col, reset_col, _ = st.columns([0.14, 0.14, 0.72])
    with run_col:
        run_clicked = st.button("Run analysis", type="primary", width="stretch")
    with reset_col:
        st.button("Reset", width="stretch", on_click=_reset_query)

if run_clicked:
    memory = load_memory(session_id) if use_memory else {}
    with st.spinner("Analyzing driver context, incentives, and policy guardrails..."):
        with _llm_mode(use_live_llm):
            result = run_copilot(query, conversation_memory=memory)
    if use_memory:
        save_memory(session_id, update_memory(memory, result))
    st.session_state.result = result

if st.session_state.result:
    _render_result(st.session_state.result)
else:
    st.markdown(
        """
        <div class="panel">
          <div class="section-title">Ready for analysis</div>
          <div class="subtle">Enter a manager question and run the copilot to retrieve driver data, tickets, incentives, and policy validation.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
