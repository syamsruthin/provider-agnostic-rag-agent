# Technical Specifications & Data Schemas

## 1. Technical Stack
- **Inference**: Provider-agnostic LLM module (`core/llm.py`). Default: Groq API (`llama-3.3-70b-versatile`). Swappable to OpenAI, Anthropic, local Ollama, or any OpenAI-compatible endpoint via config.
- **Orchestration**: LangGraph `StateGraph` with conditional routing, retry loops, validation, and ReAct-style iterative tool use.
- **Memory**: LangGraph `SqliteSaver` checkpointer for automatic conversation persistence via `thread_id`.
- **Streaming**: FastAPI SSE endpoint via LangGraph `astream_events`.
- **Backend**: FastAPI (Async)
- **Frontend**: Streamlit
- **Environment**: UV (Python 3.12)
- **Storage**: SQLite3, ChromaDB, local CSV.

## 2. LangGraph Architecture

The system is built as a **fully agentic LangGraph StateGraph** with conditional branching, self-correction loops, answer validation, and ReAct-style iterative tool use.

### A. Graph State (`HealthGuardState`)
A `TypedDict` defining the entire state flowing through the graph:

```python
class HealthGuardState(TypedDict):
    messages: Annotated[list, add_messages]  # LangGraph message history
    user_input: str                           # Original user query
    rewritten_query: str                      # After LLM-based normalization
    route_decision: str                       # SQL_TOOL | CSV_TOOL | RAG_TOOL | MULTI_TOOL
    route_reason: str                         # LLM reasoning for route choice
    tools_list: list[str]                     # Tools to execute
    tool_results: list[dict]                  # Accumulated tool outputs
    final_answer: str                         # Synthesized response
    trace_id: str                             # Unique trace identifier
    session_id: str                           # Session/thread identifier
    trace_markdown: str                       # Formatted trace for UI

    # Agentic control fields
    retry_count: int                          # Current tool retry attempts
    current_tool: str                         # Which tool is currently executing
    react_count: int                          # ReAct loop iteration counter
    validation_result: str                    # PASS/FAIL from answer validator
    error_context: str                        # Error details for retry attempts
```

### B. Graph Nodes
| Node | Function | Description |
|------|----------|-------------|
| `rewrite` | `rewrite_node()` | Input Guardrail and LLM query normalization. Calls `query_validator` to reject out-of-scope queries (sets `route_decision = FAIL_GUARDRAIL`). |
| `route` | `route_node()` | LLM-based routing. Bypasses if `FAIL_GUARDRAIL`. |
| `execute_sql` | `execute_sql_node()` | Runs SQL tool, stores result in `tool_results` |
| `execute_csv` | `execute_csv_node()` | Runs CSV/Python tool, stores result in `tool_results` |
| `execute_rag` | `execute_rag_node()` | Runs hybrid RAG search, stores result in `tool_results` |
| `execute_multi` | `execute_multi_node()` | Runs multiple tools sequentially with context enrichment between steps |
| `check_retry` | `check_retry_node()` | Inspects tool results for errors. If error + retries < 2, routes back to the failed tool with error context. Otherwise proceeds to synthesis. |
| `synthesize` | `synthesize_node()` | LLM synthesis of final answer from tool results + message history |
| `validate` | `validate_node()` | LLM checks if the answer fully addresses the user's question. Returns PASS/FAIL with reasoning. |

### C. Graph Edges (Agentic Flow)
                                  ┌→ execute_sql ──┐
START → rewrite → route ──────────┤→ execute_csv ──┤──→ check_retry ──→ [error?]
                   ↑    │         ├→ execute_rag ──┤       │               │
                   │    │         └→ execute_multi─┘       │          retry (max 2)
                   │    │                                  ↓               │
                   │    │                             synthesize ←─────────┘
                   │    │                                  │
                   │    │                             validate
                   │    │                              │      │
                   └────┼─ [FAIL + react < 2] ─────────┘      │
                        │                                     │
                        └─────── [FAIL_GUARDRAIL] ────────────┼─→ finalize → END
                                                              │
                                                            [PASS]

Key routing logic:
- **After `route`**: `add_conditional_edges` dispatches to `execute_sql`, `execute_csv`, `execute_rag`, or `execute_multi` based on `route_decision`.
- **After `check_retry`**: If tool returned an error and `retry_count < 2`, loops back to the same execute node with `error_context` injected. Otherwise → `synthesize`.
- **After `validate`**: If `FAIL` and `react_count < 2`, loops back to `route` (ReAct pattern). If `PASS` or max retries exhausted → `END`.

### D. Self-Correction Retry Loop
When a tool execution fails (e.g., invalid SQL, Python error), the graph:
1. Increments `retry_count` in state.
2. Sets `error_context` to the error message + failed code.
3. Routes back to the same execute node via conditional edge.
4. The execute node sees `error_context` and passes it to the LLM as context for re-generation.
5. Maximum 2 retries before falling through to synthesis with the error.

### E. Answer Validation & ReAct Loop
After synthesis, the `validate` node asks the LLM:
> "Does this answer fully and accurately address the user's question? Is any critical information missing?"

- **PASS**: Answer is complete → `END`.
- **FAIL**: Answer is incomplete or wrong. If `react_count < 2`, the validator's reasoning is injected into the state and the graph loops back to `route` for a second attempt (possibly with a different tool). This is the **ReAct (Reason + Act)** pattern.

### F. Memory & Persistence

#### Conversation Memory (per-session)
- **Checkpointer**: `SqliteSaver` from `langgraph-checkpoint-sqlite`.
- **Persistence DB**: `backend/data/checkpoints.db` (SQLite).
- **Thread scoping**: Each conversation session maps to a LangGraph `thread_id`.
- **Automatic history**: LangGraph's `add_messages` annotation handles appending.
- **Coreference Resolution**: The `rewrite` node extracts the last 10 messages from the state and passes them to the query rewriter, allowing the LLM to resolve pronouns and implicit references (e.g., turning "Which of those has the lowest deductible?" into "Which Silver plan has the lowest deductible...").

### G. Streaming
- **Endpoint**: `POST /chat/stream` returns Server-Sent Events (SSE).
- **Implementation**: Uses LangGraph's `astream_events(input, config)` to emit events as each node completes.
- **Event types**: `node_start`, `node_complete`, `tool_result`, `final_answer`.
- **Frontend**: Streamlit can consume SSE to show live progress (which node is running, intermediate results).

## 3. Modular Tool Architecture

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

### C. LLM Abstraction Layer (`core/llm.py`)
All LLM interactions go through a single provider-agnostic module. No file in the codebase directly imports a provider SDK (Groq, OpenAI, etc.).

```python
from backend.core.llm import llm_completion

# Every LLM call in the system uses this interface:
response_text = llm_completion(
    messages=[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
    temperature=0,
    max_tokens=512,
)
```

**Plugging in a new LLM provider:**
1. Set `LLM_PROVIDER` in `config.py` (e.g., `"openai"`, `"groq"`, `"ollama"`).
2. Set the corresponding env vars (`OPENAI_API_KEY`, `GROQ_API_KEY`, etc.).
3. Optionally set `LLM_MODEL` and `LLM_BASE_URL` for custom endpoints.
4. Zero code changes needed in any other file — the router, tools, orchestrator, and all agents call `llm_completion()` which internally dispatches to the configured provider.

## 4. Data Schema Definitions

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

### D. Conversation Memory (LangGraph Checkpointer)
**Database**: `checkpoints.db`
Managed entirely by `langgraph-checkpoint-sqlite`. State is serialized as LangGraph checkpoints, scoped by `thread_id` (= session ID).

- **Persistence**: Conversations survive server restarts automatically.
- **Scalability**: LangGraph handles checkpoint pruning and state management.
- **Concurrency**: SQLite WAL mode via the checkpointer.

## 5. Agent Prompt Engineering

### Query Rewriter System Prompt (LLM-based)
> "You are a query rewriter for a US health insurance assistant.
> Your job is to normalize the user's query so downstream tools can process it accurately.
> Apply ALL of the following transformations:
> 1. Replace full US state names with 2-letter abbreviations (e.g., 'Texas' → 'TX').
> 2. Replace colloquial medical terms with exact specialty names (e.g., 'heart doctor' → 'Cardiologist', 'family doctor' → 'PCP').
> 3. Fix obvious typos and spelling errors.
> 4. Expand ambiguous abbreviations.
> Output ONLY the rewritten query. Do NOT answer the question. Preserve original intent."

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

### Answer Validator System Prompt
> "You are a quality checker for a health insurance assistant.
> Given the user's original question and the assistant's answer, determine:
> 1. Does the answer directly address the question?
> 2. Is any critical information missing?
> 3. Are the facts consistent with the tool results provided?
> Reply with EXACTLY 'PASS' or 'FAIL' on the first line, followed by a brief reason."

## 6. Logging & Tracing Logic

### Architecture: Per-Node Tracing
Every graph node logs its own step **as it executes**, not retroactively. The `TraceLogger` is passed through the graph state and accumulates entries in real time. Each step captures:
- **Step number & node name**
- **Timestamp** (UTC ISO-8601)
- **Input**: What the node received
- **Output**: What the node produced
- **Reasoning / Decision**: Why the node made the choices it did
- **Duration**: Time taken for the step

### JSONL Machine Log
One entry per node execution, appended to `{session_id}.jsonl`:
```json
{
  "timestamp": "2026-05-02T06:30:00Z",
  "trace_id": "abc-123",
  "session_id": "sess-456",
  "step": 1,
  "node": "rewrite",
  "input": "Find me a heart doctor in Texas",
  "output": "Find me a Cardiologist in TX",
  "reasoning": "LLM normalized: 'heart doctor' → 'Cardiologist', 'Texas' → 'TX'",
  "duration_ms": 320,
  "metadata": {}
}
```

### Markdown Report (Human-Readable)
Written to `trace_{trace_id}.md` — maps to every node in the graph:

```
# Trace Report: abc12345
Session: sess-456  |  Timestamp: 2026-05-02 06:30:00 UTC

---
## Step 1: Rewrite
- Input: "Find me a heart doctor in Texas"
- Output: "Find me a Cardiologist in TX"
- Changes: 'heart doctor' → 'Cardiologist', 'Texas' → 'TX'

## Step 2: Route
- Input: "Find me a Cardiologist in TX"
- Decision: CSV_TOOL
- Reasoning: "Query is about finding a doctor by specialty and location"
- Tools list: ['CSV_TOOL']

## Step 3: Execute (CSV_TOOL)  ← conditional edge fired
- Input query: "Find me a Cardiologist in TX"
- Generated code: `result = df[(df['specialty'] == 'Cardiologist') & (df['state'] == 'TX')]`
- Result: (3 rows) ...
- Error: None

## Step 4: Check Retry
- Errors found: None
- Retry count: 0/2
- Decision: → proceed to synthesize

## Step 5: Synthesize
- Input: Query + tool results (1 tool, 3 rows)
- LLM prompt tokens: ~450
- Output: "Here are the Cardiologists available in TX..."

## Step 6: Validate
- Input: Question + Answer
- Verdict: PASS
- Reason: "Answer lists TX cardiologists with full details"
- React count: 0/2
- Decision: → finalize

## Step 7: Finalize
- Final answer delivered
- Total steps: 7
- Total duration: 2.4s
```

### Retry Loop Trace (when tool fails)
When a retry occurs, it shows as additional steps:
```
## Step 3: Execute (SQL_TOOL) — Attempt 1
- Error: "no such column: plan_cost"

## Step 4: Check Retry
- Decision: → RETRY (1/2)
- Error context injected: "no such column: plan_cost"

## Step 5: Execute (SQL_TOOL) — Attempt 2 (retry)
- Error context: "Previous attempt failed: no such column: plan_cost"
- Generated code: SELECT monthly_premium FROM plan_benefits...
- Result: (5 rows)
- Error: None

## Step 6: Check Retry
- Decision: → proceed to synthesize
```

### ReAct Loop Trace (when validation fails)
```
## Step 7: Validate
- Verdict: FAIL
- Reason: "Answer only covers cost but not doctor availability"
- Decision: → re-route (react_count: 1/2)

## Step 8: Route (ReAct iteration 2)
- Decision: CSV_TOOL
- Reasoning: "Need to also find doctors..."
...
```

## 7. Extensibility Guide
To add a new data source (e.g., a `claims_history.db` or `pharmacies.csv`):
1. Define the schema config in `core/data_sources.py`.
2. Register it in the tool registry.
3. Add a new `execute_*` node in the orchestrator graph.
4. Update the Router prompt and the `route_dispatcher` conditional edge.
5. No changes needed to the execution engines, retry logic, or validation.

## 8. Strict Guardrails Framework
To ensure enterprise compliance and prevent hallucination, the system implements a 3-layer guardrail framework located in `backend/agents/guardrails.py`:

### A. Input Guardrails (Pre-Processing)
- **Component**: `query_validator`
- **Location**: Executed inside `rewrite_node`.
- **Function**: Strictly classifies user input against the Authorized Knowledge Boundary (AKB). It is designed to pass conversational follow-ups and data requests while immediately blocking undeniable out-of-scope queries (e.g., general knowledge or hypotheticals).
- **Enforcement**: If out-of-scope, it sets `route_decision = FAIL_GUARDRAIL`, bypassing all tool execution and routing straight to `finalize` with a standardized fallback message.

### B. Context & LLM Guardrails
- **Component**: `context_validator` and Strict System Prompting
- **Location**: Executed inside `synthesize_node`.
- **Function**: Evaluates if the full context (retrieved tool data, **executed code/SQL**, and recent conversation history) is sufficient to logically answer the query. If insufficient, bypasses LLM generation and returns a fallback message.
- **Enforcement**: The synthesis LLM is given a strict system prompt overriding all prior knowledge, mandating responses ONLY from the retrieved context and history.

### C. Output Guardrails (Post-Processing)
- **Component**: `response_validator`
- **Location**: Executed inside `validate_node`.
- **Function**: Validates that the synthesized response is completely grounded in the full context (tool data, **executed code**, conversation history, **and the user query itself**). This ensures the guardrail does not falsely flag correct memory-based follow-ups or logical derivations from executed code as hallucinations.
- **Enforcement**: If hallucination or external knowledge is detected, the validator rejects the answer, replaces it with a standardized fallback, and routes to `finalize`.