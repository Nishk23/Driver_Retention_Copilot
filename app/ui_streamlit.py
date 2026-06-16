import json
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from graph.workflow import run_copilot
from state.memory import load_memory, save_memory, update_memory


st.set_page_config(page_title="Driver Retention Copilot", layout="wide")
st.title("Driver Retention Copilot")

session_id = st.sidebar.text_input("Session ID", value="streamlit-demo")
query = st.text_area(
    "Manager question",
    value=(
        "Driver Maria D-456 just called. She waited in the airport queue for two hours only to be given "
        "a 1.5km trip. She's furious as this has happened multiple times. How do we handle this?"
    ),
    height=120,
)

if st.button("Run analysis", type="primary"):
    memory = load_memory(session_id)
    result = run_copilot(query, conversation_memory=memory)
    save_memory(session_id, update_memory(memory, result))

    st.subheader("Final Recommendation")
    st.text(result.get("final_answer", "No final answer generated."))

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Driver Summary")
        st.json(result.get("driver_profile") or {})
        st.subheader("Support Evidence")
        st.json(result.get("support_tickets") or [])
    with col2:
        st.subheader("Strategist Plan")
        st.json(result.get("strategist_plan") or {})
        st.subheader("Compliance Verdict")
        st.json(result.get("critic_verdict") or {})

    st.subheader("Evaluation Trace")
    st.code(json.dumps(result.get("trace", []), indent=2), language="json")
