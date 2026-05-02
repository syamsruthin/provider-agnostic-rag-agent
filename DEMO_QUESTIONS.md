# HealthGuard Demo Questions

## 🔵 SQL_TOOL — Plan & Cost Queries
> *Conditional routing sends these directly to `execute_sql` node*

1. Which plan has the lowest monthly premium?
2. Show me all Gold plans
3. Which plans have a deductible less than $2000?
4. What is the average specialist copay across all plans?
5. Compare the emergency room copay for Platinum plans

## 🟢 CSV_TOOL — Doctor & Provider Queries
> *Conditional routing sends these directly to `execute_csv` node*

6. Find me a Dermatologist in Austin, TX
7. How many Cardiologists are in New York?
8. List all doctors accepting new patients in Seattle, WA
9. Find a primary care physician in California
   > *Triggers LLM rewrite: "primary care" → PCP, "California" → CA*
10. Show me Tier 1 Pediatricians in Chicago

## 🟡 RAG_TOOL — Policy & Document Queries
> *Conditional routing sends these directly to `execute_rag` node*

11. What are the policy exclusions for cosmetic surgery?
12. How do I file an out-of-network claim?
13. What are my rights as a member?
14. Is bariatric surgery covered under the plan?
15. What is the appeals process for a denied claim?

## 🟣 MULTI_TOOL — Cross-Source Complex Queries ⭐
> *Conditional routing sends these to `execute_multi` — tools run sequentially with context enrichment*

16. I need a Dermatologist in Austin, TX under a plan with a deductible less than $1000
    > *SQL_TOOL + CSV_TOOL — sequential execution, SQL results enrich the CSV query context*
17. Find me a heart doctor in Texas with a plan that has low copays
    > *Triggers LLM rewrite: "heart doctor" → Cardiologist, "Texas" → TX, then MULTI_TOOL*
18. I want a Pediatrician in Florida and need to know about claim filing procedures
    > *CSV_TOOL + RAG_TOOL*

## 🔁 Self-Correction Retry Loop Demo
> *If SQL/Python code generation fails, the graph loops back to the same tool node (max 2 retries) with the error message injected as context*

19. Show me the total premium savings between the cheapest Bronze and most expensive Platinum plan
    > *Complex SQL — if the first query has a syntax error, watch the trace for retry attempts with error context*
20. Calculate the average copay difference between Tier 1 and Tier 2 providers by specialty
    > *Complex pandas code — likely triggers a retry if the first code attempt fails*

## ✅ Answer Validation & ReAct Loop Demo
> *After synthesis, the `validate` node checks answer quality. On FAIL, the graph re-routes (max 2 loops)*

21. What are my options for a low-cost plan with good specialist coverage?
    > *Vague query — validator may FAIL the first answer and trigger re-routing to a different tool for more complete info*
22. Can I see a Neurologist out of network, and what would it cost?
    > *May need both RAG (out-of-network rules) + SQL (cost data) — if the first route only hits one, the ReAct loop catches it*

## 🔄 Conversation Memory Demo
> *LangGraph SqliteSaver checkpointer persists state across turns via `thread_id`*

Ask these **in sequence** within the same session:
23. What Silver plans are available?
24. Which of those has the lowest deductible?
    > *Uses conversation history to understand "those" = Silver plans*
25. How does that plan compare to the cheapest Gold plan?
    > *Chains further — "that plan" references the answer from #24*

## ⚡ LLM Query Rewriter Showcase
> *The `rewrite` node uses an LLM to normalize queries — check the trace sidebar to see the rewrite*

These highlight the LLM rewriter's capabilities:
- Find me a skin doctor in Washington → *"Dermatologist in WA"*
- I need a bone doctor in Massachusetts → *"Orthopedic Surgeon in MA"*
- Eye doctor in New Jersey → *"Ophthalmologist in NJ"*
- Get me a tummy doctor in Cali → *"Gastroenterologist in CA" (handles slang + abbreviation)*
- Lung docter in Pensylvania → *"Pulmonologist in PA" (fixes typos)*

## 📡 Streaming Endpoint Demo
> *Use `POST /chat/stream` instead of `/chat` to receive SSE events as each node completes*

```bash
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Find me a Cardiologist in New York", "session_id": "demo-123"}' \
  --no-buffer
```
Events arrive as each node fires: `rewrite` → `route` → `execute_csv` → `check_retry` → `synthesize` → `validate` → `finalize`.

---

## Suggested Demo Flow

### Quick Demo (5 min)
1. **#1** (SQL) — simple, fast, shows conditional routing to `execute_sql`
2. **#6** (CSV) — doctor search, shows conditional routing to `execute_csv`
3. **#11** (RAG) — policy knowledge, shows conditional routing to `execute_rag`
4. **#16** (MULTI) — the showstopper, show sequential tool chaining in trace
5. **#9** (rewrite) — point out LLM rewrite in trace ("primary care → PCP")

### Full Demo (10 min)
6. **#19** (retry) — trigger a self-correction loop, show retry count in trace
7. **#21** (validation) — show the validate node PASS/FAIL in trace
8. **#23 → #24 → #25** (memory) — conversation continuity across turns
9. **curl /chat/stream** — show real-time SSE events in terminal

### Architecture Walkthrough
Point out in the trace sidebar:
- **Graph flow**: `rewrite → route → execute_* → check_retry → synthesize → validate → finalize`
- **Conditional edges**: Different execute nodes fire based on routing decision
- **Retry loops**: `check_retry` → back to execute node with error context
- **ReAct loops**: `validate` → FAIL → `react_reroute` → `route` (re-attempts)
