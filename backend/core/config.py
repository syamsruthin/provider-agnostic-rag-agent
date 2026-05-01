"""
Centralized configuration for the HealthGuard backend.
All paths, model settings, and environment variables in one place.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent  # backend/
DATA_DIR = BACKEND_DIR / "data"
DOCS_DIR = DATA_DIR / "docs"
LOGS_DIR = BACKEND_DIR / "logs"

DB_PATH = DATA_DIR / "insurance.db"
CSV_PATH = DATA_DIR / "providers.csv"
CHROMA_DIR = DATA_DIR / "chroma_db"
MEMORY_DB_PATH = DATA_DIR / "memory.db"

# ---------------------------------------------------------------------------
# Groq / LLM
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ---------------------------------------------------------------------------
# Embedding model (for ChromaDB + sentence-transformers)
# ---------------------------------------------------------------------------
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# ---------------------------------------------------------------------------
# Agent prompts (data-source-specific prompts are in core/data_sources.py)
# ---------------------------------------------------------------------------
ROUTER_SYSTEM_PROMPT = (
    "Analyze the user query. Route to:\n"
    "1. 'SQL_TOOL': For plan costs, premiums, copays, or deductibles.\n"
    "2. 'CSV_TOOL': For finding doctors, specialties, or locations (City, State, Zip).\n"
    "3. 'RAG_TOOL': For policy rules, exclusions, member rights, or claim procedures.\n"
    "4. 'MULTI_TOOL': If the query requires a combination of the above.\n"
    "Return ONLY a valid JSON object with keys 'tool' and 'reason'. "
    "Do not include any other text."
)

