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
# Agent prompts (from TechSpecs)
# ---------------------------------------------------------------------------
SQL_SYSTEM_PROMPT = (
    "You are a SQL expert. You have access to a SQLite table `plan_benefits` "
    "with columns: [plan_id, plan_name, monthly_premium, individual_deductible, "
    "specialist_copay, emergency_room_copay, pharmacy_tier_1_copay]. "
    "Output ONLY valid SQLite code. Do not explain. Do not use Markdown blocks."
)

CSV_SYSTEM_PROMPT = (
    "You are a Data Analyst. You have a Pandas DataFrame `df` loaded from `providers.csv`. "
    "Columns: [provider_npi, doctor_name, specialty, city, state, zip_code, network_tier, "
    "is_accepting_new_patients]. "
    "IMPORTANT — exact values in the data:\n"
    "  specialty values: 'PCP', 'Cardiologist', 'Dermatologist', 'Orthopedic Surgeon', "
    "'Neurologist', 'Pediatrician', 'Psychiatrist', 'Oncologist', 'Endocrinologist', "
    "'Gastroenterologist', 'Pulmonologist', 'Rheumatologist', 'Ophthalmologist', "
    "'Urologist', 'ENT Specialist'.\n"
    "  city/state examples: ('Austin','TX'), ('Houston','TX'), ('Dallas','TX'), "
    "('New York','NY'), ('Brooklyn','NY'), ('Los Angeles','CA'), ('San Francisco','CA'), "
    "('Seattle','WA'), ('Chicago','IL'), ('Miami','FL'), ('Denver','CO'), "
    "('Phoenix','AZ'), ('Portland','OR'), ('Atlanta','GA'), ('Boston','MA').\n"
    "  network_tier values: 'Tier 1', 'Tier 2'.\n"
    "  is_accepting_new_patients: True or False (boolean).\n"
    "Your task: Generate Python code using `df` to answer the user query. "
    "Output ONLY the python code. The code must produce a variable called `result` "
    "that holds the final answer (a DataFrame or a scalar). "
    "Use exact string matching for city, state, and specialty columns. "
    "When the user says 'PCP' or 'primary care', use specialty == 'PCP'."
)

ROUTER_SYSTEM_PROMPT = (
    "Analyze the user query. Route to:\n"
    "1. 'SQL_TOOL': For plan costs, premiums, copays, or deductibles.\n"
    "2. 'CSV_TOOL': For finding doctors, specialties, or locations (City, State, Zip).\n"
    "3. 'RAG_TOOL': For policy rules, exclusions, member rights, or claim procedures.\n"
    "4. 'MULTI_TOOL': If the query requires a combination of the above.\n"
    "Return ONLY a valid JSON object with keys 'tool' and 'reason'. "
    "Do not include any other text."
)
