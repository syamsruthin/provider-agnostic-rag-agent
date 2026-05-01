"""
HealthGuard Agentic RAG — Streamlit Frontend
=============================================
Chat interface with live trace sidebar, tool badges, and reasoning toggle.
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

    /* Trace sidebar */
    .trace-container {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 1rem;
        font-size: 0.82rem;
        line-height: 1.5;
        max-height: 600px;
        overflow-y: auto;
    }
    .trace-container h3 { font-size: 0.9rem; color: #334155; margin-top: 0.8rem; }
    .trace-container code {
        background: #f1f5f9;
        padding: 2px 5px;
        border-radius: 3px;
        font-size: 0.78rem;
    }

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
    st.markdown('<p class="sidebar-section">📋 Live Trace</p>', unsafe_allow_html=True)

    if st.session_state.traces:
        # Show the most recent trace, with an expander for older ones
        latest = st.session_state.traces[-1]
        st.markdown(
            f'<div class="trace-container">{latest}</div>',
            unsafe_allow_html=True,
        )

        if len(st.session_state.traces) > 1:
            with st.expander(f"📜 Previous traces ({len(st.session_state.traces) - 1})"):
                for i, t in enumerate(reversed(st.session_state.traces[:-1])):
                    st.markdown(f"**Turn {len(st.session_state.traces) - 1 - i}**")
                    st.markdown(t)
                    st.divider()
    else:
        st.info("Ask a question to see the agent's reasoning trace here.")

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

                # Display answer
                st.markdown(answer)

                # Tool badges
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
