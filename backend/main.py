"""
HealthGuard Agentic RAG — FastAPI Backend
==========================================
Entry point for the backend API server.
"""

import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown hooks
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify data files exist. Shutdown: cleanup."""
    from pathlib import Path

    data_dir = Path(__file__).parent / "data"
    db_path = data_dir / "insurance.db"
    csv_path = data_dir / "providers.csv"
    docs_dir = data_dir / "docs"

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

    print("🚀 HealthGuard API started.")
    yield
    print("👋 HealthGuard API shutdown.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="HealthGuard Agentic RAG",
    description="Multi-modal health insurance assistant powered by Groq LLama-3",
    version="0.1.0",
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "healthguard-api"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chat endpoint.
    Accepts user_input and session_id, routes to agents, returns synthesized answer.
    (Stub — will be implemented in Milestone 2-3)
    """
    trace_id = str(uuid.uuid4())

    return ChatResponse(
        session_id=request.session_id,
        trace_id=trace_id,
        answer=(
            f"🏗️ HealthGuard is under construction. "
            f"Your question: '{request.user_input}' "
            f"(session: {request.session_id[:8]}..., trace: {trace_id[:8]}...)"
        ),
        tools_used=[],
        trace_markdown="*Trace will be generated once agents are implemented.*",
    )


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
