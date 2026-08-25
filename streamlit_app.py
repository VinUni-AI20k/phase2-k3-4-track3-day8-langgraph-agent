"""Streamlit Interactive Web UI for LangGraph Support Agent.

Run with: streamlit run streamlit_app.py
"""

from __future__ import annotations

import json
from time import perf_counter
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.scenarios import load_scenarios
from langgraph_agent_lab.state import Route, Scenario, initial_state

load_dotenv()

st.set_page_config(
    page_title="LangGraph Agentic Orchestration Lab",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #4B5563;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F3F4F6;
        border-radius: 10px;
        padding: 1rem;
        border-left: 5px solid #3B82F6;
        margin-bottom: 1rem;
    }
    .route-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .route-simple { background-color: #E0E7FF; color: #3730A3; }
    .route-tool { background-color: #DBEAFE; color: #1E40AF; }
    .route-missing { background-color: #FEF3C7; color: #92400E; }
    .route-risky { background-color: #FEE2E2; color: #991B1B; }
    .route-error { background-color: #FCE7F3; color: #9D174D; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="main-header">🤖 LangGraph Agentic Support Orchestrator</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Production-grade LangGraph workflow with LLM intent routing, '
    'state persistence, bounded retry loops, and HITL approval.</div>',
    unsafe_allow_html=True,
)

# Sidebar Configuration
st.sidebar.header("⚙️ Workflow Configuration")

checkpointer_kind = st.sidebar.selectbox(
    "Persistence Backend",
    options=["memory", "sqlite"],
    index=0,
    help="Select checkpointer mechanism for state persistence and replay.",
)

# Load sample scenarios
sample_scenarios: list[Scenario] = []
try:
    sample_scenarios = load_scenarios("data/sample/scenarios.jsonl")
except Exception:
    pass

scenario_options = ["Custom Query"] + [f"{s.id}: {s.query[:45]}..." for s in sample_scenarios]
selected_scenario_idx = st.sidebar.selectbox(
    "Select Scenario Preset",
    options=range(len(scenario_options)),
    format_func=lambda i: scenario_options[i],
)

if selected_scenario_idx > 0 and sample_scenarios:
    preset = sample_scenarios[selected_scenario_idx - 1]
    default_query = preset.query
    default_route = preset.expected_route.value
    default_max_attempts = preset.max_attempts
else:
    default_query = "Please lookup order status for order 12345"
    default_route = "tool"
    default_max_attempts = 3

query_input = st.text_area("Customer Ticket / Query:", value=default_query, height=100)

col_cfg1, col_cfg2, col_cfg3 = st.columns(3)
with col_cfg1:
    expected_route_input = st.selectbox(
        "Expected Route (for grading/metric comparison):",
        options=["simple", "tool", "missing_info", "risky", "error"],
        index=["simple", "tool", "missing_info", "risky", "error"].index(default_route)
        if default_route in ["simple", "tool", "missing_info", "risky", "error"]
        else 0,
    )
with col_cfg2:
    max_attempts_input = st.number_input(
        "Max Retry Attempts:", min_value=1, max_value=5, value=default_max_attempts
    )
with col_cfg3:
    thread_id_input = st.text_input("Thread ID:", value=f"session-{int(perf_counter() * 1000) % 10000}")

run_btn = st.button("🚀 Run Workflow", type="primary", use_container_width=True)

if run_btn and query_input.strip():
    scenario_obj = Scenario(
        id=thread_id_input,
        query=query_input.strip(),
        expected_route=Route(expected_route_input),
        max_attempts=int(max_attempts_input),
    )
    init_st = initial_state(scenario_obj)
    init_st["thread_id"] = thread_id_input

    with st.spinner("Executing LangGraph workflow..."):
        start_time = perf_counter()
        checkpointer = build_checkpointer(checkpointer_kind)
        graph = build_graph(checkpointer=checkpointer)
        run_config = {"configurable": {"thread_id": thread_id_input}}

        try:
            final_state = graph.invoke(init_st, config=run_config)
            elapsed_ms = round((perf_counter() - start_time) * 1000)
            st.success(f"Workflow finished successfully in {elapsed_ms} ms!")

            # Summary Metrics
            res_col1, res_col2, res_col3, res_col4 = st.columns(4)
            actual_route = final_state.get("route", "unknown")
            events: list[dict[str, Any]] = final_state.get("events", [])
            retries = sum(1 for e in events if e.get("node") == "retry")
            interrupts = sum(1 for e in events if e.get("node") == "approval")

            res_col1.metric("Classified Route", actual_route.upper())
            res_col2.metric("Nodes Visited", len(events))
            res_col3.metric("Total Retries", retries)
            res_col4.metric("Latency", f"{elapsed_ms} ms")

            # Final Answer Section
            st.subheader("💬 Assistant Final Response")
            final_ans = final_state.get("final_answer") or final_state.get("pending_question")
            st.info(final_ans or "No response returned.")

            # Tab details
            tab_events, tab_state, tab_diagram, tab_history = st.tabs(
                ["📜 Audit Trail (Events)", "🔍 State Details", "📊 Graph Topology", "🕰️ Checkpoint History"]
            )

            with tab_events:
                st.write("### Sequential Execution Log")
                for i, ev in enumerate(events, 1):
                    node_name = ev.get("node", "unknown")
                    msg = ev.get("message", "")
                    meta = ev.get("metadata", {})
                    st.markdown(
                        f"**Step {i}: `{node_name}`** — {msg}  \n"
                        f"<small style='color:gray;'>Metadata: {json.dumps(meta, ensure_ascii=False)}</small>",
                        unsafe_allow_html=True,
                    )
                    st.divider()

            with tab_state:
                st.json(final_state)

            with tab_diagram:
                st.write("### Mermaid Graph Representation")
                mermaid_code = graph.get_graph().draw_mermaid()
                st.code(mermaid_code, language="mermaid")

            with tab_history:
                st.write("### Snapshots from Checkpointer")
                try:
                    snapshots = list(graph.get_state_history(run_config))
                    if snapshots:
                        st.write(f"Total recorded snapshots: **{len(snapshots)}**")
                        for idx, snap in enumerate(snapshots):
                            st.write(f"**Checkpoint #{idx + 1}** — Next: `{snap.next}`")
                            st.json(snap.values)
                    else:
                        st.info("No checkpoint snapshots found.")
                except Exception as exc:
                    st.warning(f"Could not load state history: {exc}")

        except Exception as err:
            st.error(f"Workflow execution failed: {err}")

# Architecture Explanation & Footer
with st.expander("📖 Architecture & Rubric Information"):
    st.markdown(
        """
        - **Intake Node:** Normalizes query text and starts audit trail.
        - **Classify Node:** Real LLM invocation with Pydantic structured output (`IntentClassification`).
        - **Tool Node:** Simulates database/service lookups with retry error simulation.
        - **Evaluate Node:** LLM-as-judge quality evaluator determining whether tool output passes or retries.
        - **Approval Node:** Human-In-The-Loop gate for sensitive/risky actions (refunds, cancellations).
        - **Retry / Dead Letter Node:** Bounded retry counter avoiding infinite loops, routing to dead letter when exhausted.
        - **Finalize Node:** Audit completion node wired to `END`.
        """
    )
