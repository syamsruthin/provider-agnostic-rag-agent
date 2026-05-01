# Technical Specifications & Data Schemas

## 1. Technical Stack
- **Inference**: Groq API (`llama3-70b-8192`)
- **Orchestration**: LangGraph or custom Agent class.
- **Backend**: FastAPI (Async)
- **Frontend**: Streamlit
- **Environment**: UV (Python 3.12)
- **Storage**: SQLite3, ChromaDB, local CSV.

## 2. Data Schema Definitions

### A. SQL Knowledge Base (SQLite)
**Table**: `plan_benefits`
- `plan_id` (TEXT, PK): e.g., 'BRZ-001'
- `plan_name` (TEXT): 'Bronze Basic', 'Silver Plus', 'Gold Elite'
- `monthly_premium` (REAL)
- `individual_deductible` (REAL)
- `specialist_copay` (REAL)
- `emergency_room_copay` (REAL)
- `pharmacy_tier_1_copay` (REAL)

### B. CSV Knowledge Base (Provider Network)
**File**: `providers.csv`
- `provider_npi` (INT): National Provider Identifier
- `doctor_name` (STR)
- `specialty` (STR): 'PCP', 'Cardiologist', 'Dermatologist', etc.
- `city` (STR)
- `state` (STR): 2-letter abbreviation (e.g., 'NY', 'CA', 'TX')
- `zip_code` (INT)
- `network_tier` (STR): 'Tier 1', 'Tier 2'
- `is_accepting_new_patients` (BOOL)

### C. Text Knowledge Base (Unstructured)
- **Files**: `exclusions.md`, `rights.md`, `claims.md`.
- **Vector Engine**: ChromaDB (all-MiniLM-L6-v2 embeddings).
- **Keyword Engine**: RankBM25.

## 3. Agent Prompt Engineering

### SQL Agent System Prompt
> "You are a SQL expert. You have access to a SQLite table `plan_benefits` with columns: [plan_id, plan_name, monthly_premium, individual_deductible, specialist_copay, emergency_room_copay, pharmacy_tier_1_copay]. 
> Output ONLY valid SQLite code. Do not explain. Do not use Markdown blocks."

### CSV/Python Agent System Prompt
> "You are a Data Analyst. You have a Pandas DataFrame `df` loaded from `providers.csv`. 
> Columns: [provider_npi, doctor_name, specialty, city, state, zip_code, network_tier, is_accepting_new_patients].
> Your task: Generate Python code using `df` to answer the user query. Output ONLY the python code."

### Router System Prompt
> "Analyze the user query. Route to:
> 1. 'SQL_TOOL': For plan costs, premiums, or deductibles.
> 2. 'CSV_TOOL': For finding doctors, specialties, or locations (City, State, Zip).
> 3. 'RAG_TOOL': For policy rules, exclusions, or rights.
> 4. 'MULTI_TOOL': If the query requires a combination.
> Return JSON with 'tool' and 'reason'."

## 4. Logging & Tracing Logic
For every `trace_id`:
1.  **JSONL Entry**: `{"timestamp": "...", "trace_id": "...", "component": "Router", "input": "...", "output": "...", "reasoning": "..."}`
2.  **Markdown Report**:
    - **User Query**: ...
    - **Step 1: Rewrite**: New query string.
    - **Step 2: Router Decision**: Why the tool(s) were chosen.
    - **Step 3: Tool Execution**: Raw SQL/Code generated and Result.
    - **Step 4: Final Synthesis**: How the LLM combined results.