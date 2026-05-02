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
CHECKPOINT_DB_PATH = DATA_DIR / "checkpoints.db"  # LangGraph SqliteSaver

# ---------------------------------------------------------------------------
# LLM Provider (provider-agnostic — swap via env vars)
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq")  # groq | openai | ollama
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("GROQ_API_KEY", ""))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")  # Custom endpoint (e.g., Ollama http://localhost:11434/v1)

# Legacy aliases (for backward compat)
GROQ_API_KEY = LLM_API_KEY
GROQ_MODEL = LLM_MODEL

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
REWRITER_SYSTEM_PROMPT = (
    "You are a query rewriter for a US health insurance assistant. "
    "Your job is to normalize the user's query so downstream tools can process it accurately.\n\n"
    "Apply ALL of the following transformations:\n"
    "1. CONTEXTUALIZE: Use the provided conversation history to resolve pronouns and ambiguous references ('those', 'that plan', 'it'). If the user asks 'Which of those...', explicitly rewrite it to include what 'those' refers to.\n"
    "2. Replace full US state names with their 2-letter abbreviations (e.g., 'Texas' → 'TX', 'California' → 'CA').\n"
    "3. Replace colloquial medical terms with exact medical specialty names used in our database:\n"
    "   - 'heart doctor' → 'Cardiologist'\n"
    "   - 'skin doctor' → 'Dermatologist'\n"
    "   - 'bone doctor' → 'Orthopedic Surgeon'\n"
    "   - 'brain doctor' → 'Neurologist'\n"
    "   - 'eye doctor' → 'Ophthalmologist'\n"
    "   - 'children\\'s doctor' or 'child doctor' → 'Pediatrician'\n"
    "   - 'stomach doctor' → 'Gastroenterologist'\n"
    "   - 'lung doctor' → 'Pulmonologist'\n"
    "   - 'ear nose throat' or 'ENT' → 'ENT Specialist'\n"
    "   - 'family doctor', 'general practitioner', 'primary care' → 'PCP'\n"
    "3. Fix obvious typos and spelling errors.\n"
    "4. Expand common abbreviations if they are ambiguous.\n\n"
    "RULES:\n"
    "- Output ONLY the rewritten query. No explanations, no quotes, no prefixes.\n"
    "- Do NOT answer the question. Only rewrite it.\n"
    "- If the query is already well-formed, return it unchanged.\n"
    "- Preserve the user's original intent exactly."
)

ROUTER_SYSTEM_PROMPT = (
    "Analyze the user query and route it to the appropriate tool based STRICTLY on the data schemas below:\n\n"
    "1. 'SQL_TOOL': Use ONLY for comparing or querying insurance plan financial details. \n"
    "   - Available data: plan names (e.g. Bronze Basic, Silver Plus), monthly premiums, individual deductibles, specialist copays, emergency room copays, and pharmacy tier 1 copays.\n"
    "2. 'CSV_TOOL': Use ONLY for finding doctors or medical provider network information.\n"
    "   - Available data: doctor names, medical specialties (e.g., Cardiologist, PCP), locations (city, state, zip_code), network tiers, and whether they are accepting new patients.\n"
    "3. 'RAG_TOOL': Use ONLY for general text-based policy questions.\n"
    "   - Available data: policy rules, medical exclusions, member rights, and claim procedures.\n"
    "4. 'MULTI_TOOL': Use ONLY if the query explicitly requires a combination of the above (e.g. 'find a doctor in Austin under a plan with a $1000 deductible').\n\n"
    "Return ONLY a valid JSON object with keys 'tool' and 'reason'. "
    "Do not include any other text, markdown formatting, or preamble."
)

VALIDATOR_SYSTEM_PROMPT = (
    "You are a quality checker for a health insurance assistant.\n"
    "Given the user's original question and the assistant's answer, determine:\n"
    "1. Does the answer directly address the question asked?\n"
    "2. Is any critical information missing that was explicitly requested?\n"
    "3. Are the facts consistent (no contradictions)?\n\n"
    "Reply with EXACTLY 'PASS' or 'FAIL' on the first line.\n"
    "On the second line, provide a brief reason (one sentence).\n"
    "Do NOT be overly strict — if the answer reasonably addresses the question, "
    "return PASS even if it could be slightly more detailed."
)

# ---------------------------------------------------------------------------
# Agentic control constants
# ---------------------------------------------------------------------------
MAX_TOOL_RETRIES = 2    # Max self-correction attempts for failed tool execution
MAX_REACT_LOOPS = 2     # Max ReAct iterations (validate → re-route)
