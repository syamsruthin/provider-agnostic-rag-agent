"""
HealthGuard Agentic RAG — FastAPI Backend
==========================================
Entry point for the backend API server.
Wires the /chat endpoint to the full orchestration pipeline.
"""

import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown hooks
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify data files, warm up RAG index. Shutdown: cleanup."""
    from pathlib import Path
    from backend.core.config import DATA_DIR, LOGS_DIR

    db_path = DATA_DIR / "insurance.db"
    csv_path = DATA_DIR / "providers.csv"
    docs_dir = DATA_DIR / "docs"

    missing = []
    if not db_path.exists():
        missing.append(str(db_path))
    if not csv_path.exists():
        missing.append(str(csv_path))
    if not docs_dir.exists():
        missing.append(str(docs_dir))

    if missing:
        print(
            "⚠️  Missing data files. Run 'python -m backend.scripts.setup_data' first.\n"
            f"   Missing: {missing}"
        )

    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Warm up the RAG index (downloads embedding model + indexes docs)
    try:
        from backend.agents.rag_agent import index_documents
        count = index_documents()
        print(f"✅ RAG index ready — {count} chunks")
    except Exception as e:
        print(f"⚠️  RAG index warm-up failed: {e}")

    print("🚀 HealthGuard API started.")
    yield
    print("👋 HealthGuard API shutdown.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="HealthGuard Agentic RAG",
    description="Multi-modal health insurance assistant powered by Groq LLama-3",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    user_input: str = Field(..., min_length=1, description="The user's question.")
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Session ID for conversation continuity.",
    )


class ChatResponse(BaseModel):
    session_id: str
    trace_id: str
    answer: str
    tools_used: list[str] = []
    trace_markdown: str = ""


class HistoryResponse(BaseModel):
    session_id: str
    exchanges: list[dict]
    total: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "healthguard-api", "version": "0.2.0"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint.
    Accepts user_input and session_id, runs the full orchestration pipeline
    (Rewrite → Route → Execute → Synthesize), returns the answer with trace.
    """
    from backend.agents.orchestrator import process_query

    try:
        result = process_query(
            user_input=request.user_input,
            session_id=request.session_id,
        )
        return ChatResponse(
            session_id=result["session_id"],
            trace_id=result["trace_id"],
            answer=result["answer"],
            tools_used=result["tools_used"],
            trace_markdown=result["trace_markdown"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")


@app.get("/history/{session_id}", response_model=HistoryResponse)
async def get_history(session_id: str):
    """Retrieve conversation history for a session."""
    from backend.core.memory import memory

    exchanges = memory.get_full_history(session_id)
    return HistoryResponse(
        session_id=session_id,
        exchanges=exchanges,
        total=len(exchanges),
    )


@app.delete("/history/{session_id}")
async def clear_history(session_id: str):
    """Clear conversation history for a session."""
    from backend.core.memory import memory

    memory.clear(session_id)
    return {"status": "cleared", "session_id": session_id}


# ---------------------------------------------------------------------------
# Entrypoint (for `python -m backend.main` or direct run)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=os.getenv("BACKEND_HOST", "0.0.0.0"),
        port=int(os.getenv("BACKEND_PORT", "8000")),
        reload=True,
    )
