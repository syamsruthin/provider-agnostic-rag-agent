"""
HealthGuard Agentic RAG — Streamlit Frontend
=============================================
Chat interface with a live trace sidebar.
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
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2rem;
        font-weight: 700;
        color: #1a73e8;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #5f6368;
        margin-bottom: 2rem;
    }
    .trace-box {
        background-color: #f8f9fa;
        border-left: 4px solid #1a73e8;
        padding: 1rem;
        border-radius: 4px;
        font-family: monospace;
        font-size: 0.85rem;
        white-space: pre-wrap;
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
if "last_trace" not in st.session_state:
    st.session_state.last_trace = ""
if "show_reasoning" not in st.session_state:
    st.session_state.show_reasoning = True

# ---------------------------------------------------------------------------
# Sidebar — Trace & Settings
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    st.session_state.show_reasoning = st.toggle(
        "Show System Reasoning", value=st.session_state.show_reasoning
    )
    st.divider()

    st.markdown("### 📋 Live Trace")
    if st.session_state.last_trace:
        st.markdown(
            f'<div class="trace-box">{st.session_state.last_trace}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("Ask a question to see the agent's reasoning trace here.")

    st.divider()
    st.caption(f"Session: `{st.session_state.session_id[:8]}...`")
    if st.button("🔄 New Session"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.last_trace = ""
        st.rerun()

# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------
st.markdown('<div class="main-header">🛡️ HealthGuard Assistant</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">'
    "Your intelligent health insurance companion — powered by Agentic RAG"
    "</div>",
    unsafe_allow_html=True,
)

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Ask about plans, providers, or policies..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Call backend
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = httpx.post(
                    f"{BACKEND_URL}/chat",
                    json={
                        "user_input": prompt,
                        "session_id": st.session_state.session_id,
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()

                answer = data.get("answer", "No response received.")
                trace_md = data.get("trace_markdown", "")
                tools = data.get("tools_used", [])

                st.markdown(answer)

                if tools and st.session_state.show_reasoning:
                    st.caption(f"🔧 Tools used: {', '.join(tools)}")

                # Update state
                st.session_state.messages.append(
                    {"role": "assistant", "content": answer}
                )
                st.session_state.last_trace = trace_md

            except httpx.ConnectError:
                err = "⚠️ Cannot connect to backend. Is the FastAPI server running on `localhost:8000`?"
                st.error(err)
                st.session_state.messages.append(
                    {"role": "assistant", "content": err}
                )
            except Exception as e:
                err = f"⚠️ Error: {e}"
                st.error(err)
                st.session_state.messages.append(
                    {"role": "assistant", "content": err}
                )
