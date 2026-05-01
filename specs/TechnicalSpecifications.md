# Technical Specifications & Data Schemas

## 1. Technical Stack
- **Inference**: Groq API (`llama-3.3-70b-versatile`)
- **Orchestration**: LangGraph or custom Agent class.
- **Backend**: FastAPI (Async)
- **Frontend**: Streamlit
- **Environment**: UV (Python 3.12)
- **Storage**: SQLite3, ChromaDB, local CSV.
- **Memory**: SQLite-backed conversation persistence (`memory.db`).

## 2. Modular Tool Architecture

The SQL and Python execution capabilities are built as **data-source-agnostic engines** in `backend/core/tools.py`, separate from the data-source-specific agent wrappers in `backend/agents/`.

### A. Execution Engines (`core/tools.py`)

#### `SQLExecutionEngine`
A reusable engine that takes a database path, a schema description, and a system prompt, then:
1. Generates SQL from natural language via the configured LLM.
2. Executes it against the given SQLite database.
3. Returns structured results (raw + formatted).

Can be instantiated for **any** SQLite database — not coupled to `insurance.db`.

#### `PythonExecutionEngine`
A reusable engine that takes a DataFrame (or CSV path), a schema description, and a system prompt, then:
1. Generates pandas code from natural language via the configured LLM.
2. Executes it in a sandboxed namespace with configurable allowed modules.
3. Returns structured results.

Can be instantiated for **any** CSV/DataFrame — not coupled to `providers.csv`.

### B. Data Source Configurations (`core/data_sources.py`)
Each data source is defined as a configuration dict containing:
- `name`: Human-readable identifier (e.g., `"plan_benefits"`)
- `type`: `"sql"` or `"csv"`
- `path`: Path to the database or CSV file
- `schema`: Column names, types, and sample values for prompt engineering
- `system_prompt`: The LLM system prompt tailored to this data source

Adding a new data source = adding a new config entry + registering it in the tool registry.

## 3. Data Schema Definitions

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

### D. Conversation Memory (SQLite)
**Database**: `memory.db`  
**Table**: `conversation_history`
- `id` (INTEGER, PK, AUTOINCREMENT)
- `session_id` (TEXT, NOT NULL, INDEXED)
- `turn_index` (INTEGER, NOT NULL): Sequential turn counter per session.
- `role` (TEXT, NOT NULL): `'user'` or `'assistant'`
- `content` (TEXT, NOT NULL): The message content.
- `created_at` (TEXT, NOT NULL): ISO-8601 timestamp.

The `WindowBufferMemory` class reads only the **last N turns** (default 5 exchanges = 10 rows) per session using `ORDER BY turn_index DESC LIMIT`. This provides:
- **Persistence**: Conversations survive server restarts.
- **Scalability**: Old turns are retained for auditing but not loaded into context.
- **Concurrency**: SQLite WAL mode supports concurrent reads from FastAPI workers.

## 4. Agent Prompt Engineering

### SQL Agent System Prompt (per-data-source, injected into SQLExecutionEngine)
> "You are a SQL expert. You have access to a SQLite table `{table_name}` with columns: [{column_list}]. 
> Output ONLY valid SQLite code. Do not explain. Do not use Markdown blocks."

### CSV/Python Agent System Prompt (per-data-source, injected into PythonExecutionEngine)
> "You are a Data Analyst. You have a Pandas DataFrame `df` loaded from `{source_file}`. 
> Columns: [{column_list}].
> {schema_hints}
> Your task: Generate Python code using `df` to answer the user query. Output ONLY the python code.
> The code must produce a variable called `result`."

### Router System Prompt
> "Analyze the user query. Route to:
> 1. 'SQL_TOOL': For plan costs, premiums, or deductibles.
> 2. 'CSV_TOOL': For finding doctors, specialties, or locations (City, State, Zip).
> 3. 'RAG_TOOL': For policy rules, exclusions, or rights.
> 4. 'MULTI_TOOL': If the query requires a combination.
> Return JSON with 'tool' and 'reason'."

## 5. Logging & Tracing Logic
For every `trace_id`:
1.  **JSONL Entry**: `{"timestamp": "...", "trace_id": "...", "component": "Router", "input": "...", "output": "...", "reasoning": "..."}`
2.  **Markdown Report**:
    - **User Query**: ...
    - **Step 1: Rewrite**: New query string.
    - **Step 2: Router Decision**: Why the tool(s) were chosen.
    - **Step 3: Tool Execution**: Raw SQL/Code generated and Result.
    - **Step 4: Final Synthesis**: How the LLM combined results.

## 6. Extensibility Guide
To add a new data source (e.g., a `claims_history.db` or `pharmacies.csv`):
1. Define the schema config in `core/data_sources.py`.
2. Register it in the tool registry.
3. Update the Router prompt to include the new routing option.
4. No changes needed to the execution engines themselves.