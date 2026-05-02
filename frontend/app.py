"""
HealthGuard Agentic RAG — Streamlit Frontend
=============================================
Chat interface with per-step trace sidebar, tool badges, agentic status,
and reasoning toggle.
"""

import uuid

import httpx
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BACKEND_URL = "http://localhost:8000"

st.set_page_config(
    page_title="HealthGuard Assistant",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS — Premium dark-accented design
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* Global font */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Header styling */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
        letter-spacing: -0.5px;
    }
    .sub-header {
        font-size: 1rem;
        color: #6b7280;
        margin-bottom: 1.5rem;
        font-weight: 400;
    }

    /* Tool badges */
    .tool-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 6px;
        letter-spacing: 0.3px;
    }
    .tool-sql { background: #dbeafe; color: #1e40af; }
    .tool-csv { background: #dcfce7; color: #166534; }
    .tool-rag { background: #fef3c7; color: #92400e; }
    .tool-multi { background: #ede9fe; color: #5b21b6; }

    /* Agentic status badges */
    .agentic-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 10px;
        font-size: 0.7rem;
        font-weight: 600;
        margin-right: 4px;
        margin-bottom: 4px;
    }
    .badge-retry { background: #fff7ed; color: #c2410c; border: 1px solid #fed7aa; }
    .badge-react { background: #fdf2f8; color: #be185d; border: 1px solid #fbcfe8; }
    .badge-pass { background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
    .badge-fail { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
    .badge-steps { background: #f0f9ff; color: #0369a1; border: 1px solid #bae6fd; }
    .badge-duration { background: #faf5ff; color: #7e22ce; border: 1px solid #e9d5ff; }

    /* Status indicator */
    .status-dot {
        display: inline-block;
        width: 8px;
        height: 8px;
        border-radius: 50%;
        margin-right: 6px;
    }
    .status-online { background: #22c55e; }
    .status-offline { background: #ef4444; }

    /* Sidebar section headers */
    .sidebar-section {
        font-size: 0.85rem;
        font-weight: 600;
        color: #475569;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "traces" not in st.session_state:
    st.session_state.traces = []  # List of trace markdowns
if "trace_meta" not in st.session_state:
    st.session_state.trace_meta = []  # List of {tools, trace_id, retry_count, ...}
if "show_reasoning" not in st.session_state:
    st.session_state.show_reasoning = True


# ---------------------------------------------------------------------------
# Helper: tool badge HTML
# ---------------------------------------------------------------------------
def tool_badges_html(tools: list[str]) -> str:
    badge_map = {
        "SQL_TOOL": ("SQL", "tool-sql"),
        "CSV_TOOL": ("CSV", "tool-csv"),
        "RAG_TOOL": ("RAG", "tool-rag"),
        "MULTI_TOOL": ("MULTI", "tool-multi"),
    }
    badges = []
    for t in tools:
        label, cls = badge_map.get(t, (t, "tool-multi"))
        badges.append(f'<span class="tool-badge {cls}">{label}</span>')
    return "".join(badges)


def agentic_status_html(meta: dict) -> str:
    """Build HTML badges showing agentic loop status."""
    badges = []

    # Step count
    trace_md = meta.get("trace_markdown", "")
    step_count = trace_md.count("**") // 2  # rough count from markdown bold pairs
    # Parse step count from the trace header line
    if "**Steps**:" in trace_md:
        try:
            parts = trace_md.split("**Steps**: ")[1]
            step_count = int(parts.split(" ")[0].split("|")[0].strip())
        except (IndexError, ValueError):
            pass

    if step_count > 0:
        badges.append(f'<span class="agentic-badge badge-steps">📊 {step_count} steps</span>')

    # Duration
    if "**Duration**:" in trace_md:
        try:
            dur_part = trace_md.split("**Duration**: ")[1].split("\n")[0].strip()
            badges.append(f'<span class="agentic-badge badge-duration">⏱️ {dur_part}</span>')
        except (IndexError, ValueError):
            pass

    # Retry count
    retry = meta.get("retry_count", 0)
    if retry > 0:
        badges.append(f'<span class="agentic-badge badge-retry">🔁 {retry} retries</span>')

    # React loops
    react = meta.get("react_count", 0)
    if react > 0:
        badges.append(f'<span class="agentic-badge badge-react">♻️ {react} ReAct loops</span>')

    # Validation
    validation = meta.get("validation_result", "")
    if "PASS" in validation.upper():
        badges.append('<span class="agentic-badge badge-pass">✅ Validated</span>')
    elif "FAIL" in validation.upper():
        badges.append('<span class="agentic-badge badge-fail">❌ Validation Failed</span>')

    return " ".join(badges)


# ---------------------------------------------------------------------------
# Helper: check backend health
# ---------------------------------------------------------------------------
def check_backend() -> bool:
    try:
        r = httpx.get(f"{BACKEND_URL}/health", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Sidebar — Settings, Trace, Session Info
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown('<p class="sidebar-section">⚙️ Settings</p>', unsafe_allow_html=True)

    st.session_state.show_reasoning = st.toggle(
        "Show System Reasoning", value=st.session_state.show_reasoning
    )

    # Backend status
    backend_ok = check_backend()
    status_cls = "status-online" if backend_ok else "status-offline"
    status_txt = "Connected" if backend_ok else "Disconnected"
    st.markdown(
        f'<span class="status-dot {status_cls}"></span> Backend: **{status_txt}**',
        unsafe_allow_html=True,
    )

    st.divider()

    # Live Trace
    st.markdown('<p class="sidebar-section">📋 Agent Trace</p>', unsafe_allow_html=True)

    if st.session_state.traces:
        latest_trace = st.session_state.traces[-1]
        latest_meta = st.session_state.trace_meta[-1] if st.session_state.trace_meta else {}

        # Agentic status badges
        status_html = agentic_status_html(latest_meta)
        if status_html:
            st.markdown(status_html, unsafe_allow_html=True)

        # Tool badges
        tools = latest_meta.get("tools", [])
        if tools:
            st.markdown(tool_badges_html(tools), unsafe_allow_html=True)

        # Trace markdown rendered natively by Streamlit
        st.markdown(latest_trace)

        if len(st.session_state.traces) > 1:
            with st.expander(f"📜 Previous traces ({len(st.session_state.traces) - 1})"):
                for i, t in enumerate(reversed(st.session_state.traces[:-1])):
                    idx = len(st.session_state.traces) - 1 - i
                    meta_i = st.session_state.trace_meta[idx - 1] if idx - 1 < len(st.session_state.trace_meta) else {}
                    st.markdown(f"**Turn {idx}**")
                    # Show badges for old traces too
                    old_tools = meta_i.get("tools", [])
                    if old_tools:
                        st.markdown(tool_badges_html(old_tools), unsafe_allow_html=True)
                    st.markdown(t)
                    st.divider()
    else:
        st.info("Ask a question to see the agent's per-step reasoning trace here.")

    st.divider()

    # Session controls
    st.markdown('<p class="sidebar-section">🔑 Session</p>', unsafe_allow_html=True)
    st.caption(f"ID: `{st.session_state.session_id[:12]}...`")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 New", use_container_width=True):
            st.session_state.session_id = str(uuid.uuid4())
            st.session_state.messages = []
            st.session_state.traces = []
            st.session_state.trace_meta = []
            st.rerun()
    with col2:
        if st.button("🗑️ Clear", use_container_width=True):
            try:
                httpx.delete(
                    f"{BACKEND_URL}/history/{st.session_state.session_id}",
                    timeout=5.0,
                )
            except Exception:
                pass
            st.session_state.messages = []
            st.session_state.traces = []
            st.session_state.trace_meta = []
            st.rerun()


# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------
st.markdown(
    '<div class="main-header">🛡️ HealthGuard Assistant</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-header">'
    "Your intelligent health insurance companion — powered by Agentic RAG"
    "</div>",
    unsafe_allow_html=True,
)

# Quick-start suggestions (shown only when no messages)
if not st.session_state.messages:
    st.markdown("**Try asking:**")
    suggestions = [
        "Which plan has the lowest monthly premium?",
        "Find me a Dermatologist in Austin, TX",
        "What are the policy exclusions for cosmetic surgery?",
        "I need a heart doctor in California under a plan with low deductible",
    ]
    cols = st.columns(2)
    for i, s in enumerate(suggestions):
        with cols[i % 2]:
            if st.button(f"💬 {s}", key=f"suggest_{i}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": s})
                st.rerun()

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        # Show tool badges for assistant messages
        if msg["role"] == "assistant" and msg.get("tools") and st.session_state.show_reasoning:
            st.markdown(tool_badges_html(msg["tools"]), unsafe_allow_html=True)

# Chat input
if prompt := st.chat_input("Ask about plans, providers, or policies..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("🔍 Analyzing your question..."):
            try:
                response = httpx.post(
                    f"{BACKEND_URL}/chat",
                    json={
                        "user_input": prompt,
                        "session_id": st.session_state.session_id,
                    },
                    timeout=120.0,
                )
                response.raise_for_status()
                data = response.json()

                answer = data.get("answer", "No response received.")
                trace_md = data.get("trace_markdown", "")
                tools = data.get("tools_used", [])
                trace_id = data.get("trace_id", "")
                retry_count = data.get("retry_count", 0)
                react_count = data.get("react_count", 0)
                validation_result = data.get("validation_result", "")

                # Display answer
                st.markdown(answer)

                # Tool badges + agentic status
                if tools and st.session_state.show_reasoning:
                    st.markdown(tool_badges_html(tools), unsafe_allow_html=True)
                    st.caption(f"Trace: `{trace_id[:8]}...`")

                # Update state
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "tools": tools,
                })
                st.session_state.traces.append(trace_md)
                st.session_state.trace_meta.append({
                    "tools": tools,
                    "trace_id": trace_id,
                    "retry_count": retry_count,
                    "react_count": react_count,
                    "validation_result": validation_result,
                    "trace_markdown": trace_md,
                })

                # Trigger sidebar update
                st.rerun()

            except httpx.ConnectError:
                err = (
                    "⚠️ Cannot connect to backend. Start the server with:\n\n"
                    "```bash\nuv run python -m backend.main\n```"
                )
                st.error(err)
                st.session_state.messages.append(
                    {"role": "assistant", "content": err}
                )
            except httpx.HTTPStatusError as e:
                err = f"⚠️ Server error: {e.response.status_code} — {e.response.text[:200]}"
                st.error(err)
                st.session_state.messages.append(
                    {"role": "assistant", "content": err}
                )
            except Exception as e:
                err = f"⚠️ Unexpected error: {e}"
                st.error(err)
                st.session_state.messages.append(
                    {"role": "assistant", "content": err}
                )
