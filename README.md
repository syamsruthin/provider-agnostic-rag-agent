# HealthGuard Agentic RAG

An intelligent, transparent, multi-modal assistant for US Health Insurance members.

Synthesizes information across structured databases (SQL), provider directories (CSV), and unstructured policy documents (RAG) using Groq-powered Llama 3.

## Quick Start

```bash
# Install dependencies
uv sync

# Generate synthetic data
uv run python -m backend.scripts.setup_data

# Start backend
uv run python -m backend.main

# Start frontend (separate terminal)
uv run streamlit run frontend/app.py
```

## Architecture

- **Backend**: FastAPI with async agents (Router → SQL / CSV / RAG)
- **Frontend**: Streamlit chat UI with live trace sidebar
- **LLM**: Groq API (`llama3-70b-8192`)
- **Retrieval**: Hybrid BM25 + ChromaDB vector search
