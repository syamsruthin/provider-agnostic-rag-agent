"""
Orchestrator — Fully Agentic LangGraph StateGraph
===================================================
Features:
  1. Conditional routing (add_conditional_edges) to dedicated tool nodes
  2. Self-correction retry loop for failed tool executions (max 2 retries)
  3. Answer validation node (LLM quality check)
  4. ReAct loop (validate → re-route if answer is incomplete, max 2 loops)
  5. Streaming support via astream_events
  6. Cross-session memory via LangGraph InMemoryStore

Memory is handled by LangGraph's SqliteSaver checkpointer.
Each session maps to a thread_id.
"""

import sqlite3 as _sqlite3
import time
import uuid
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver

from backend.agents.router import rewrite_query, route_query
from backend.agents.sql_agent import sql_tool
from backend.agents.csv_agent import python_tool
from backend.agents.rag_agent import rag_tool, index_documents
from backend.core.config import (
    CHECKPOINT_DB_PATH, VALIDATOR_SYSTEM_PROMPT,
    MAX_TOOL_RETRIES, MAX_REACT_LOOPS,
)
from backend.core.llm import llm_completion
from backend.core.logger import TraceLogger
from backend.agents.guardrails import (
    query_validator,
    context_validator,
    response_validator,
    FALLBACK_OUT_OF_SCOPE,
    FALLBACK_NO_DATA,
    FALLBACK_INSUFFICIENT_CONTEXT,
)

# Module-level trace registry: trace_id → TraceLogger
# Each node retrieves its logger from here to log its own step.
_trace_registry: dict[str, TraceLogger] = {}


# ═══════════════════════════════════════════════════════════════════════════
# State Definition
# ═══════════════════════════════════════════════════════════════════════════

class HealthGuardState(TypedDict):
    """Full state flowing through the agentic LangGraph pipeline."""
    messages: Annotated[list, add_messages]  # LangGraph managed message list
    user_input: str
    rewritten_query: str
    route_decision: str
    route_reason: str
    tools_list: list[str]
    tool_results: list[dict]
    final_answer: str
    trace_id: str
    session_id: str
    trace_markdown: str

    # Agentic control fields
    retry_count: int           # Current tool retry attempts
    current_tool: str          # Which tool is currently executing
    react_count: int           # ReAct loop iteration counter
    validation_result: str     # PASS/FAIL from answer validator
    error_context: str         # Error details for retry attempts


def _get_logger(state: HealthGuardState) -> TraceLogger:
    """Get or create a TraceLogger for the current trace_id."""
    tid = state.get("trace_id", "")
    sid = state.get("session_id", "")
    if tid not in _trace_registry:
        _trace_registry[tid] = TraceLogger(trace_id=tid, session_id=sid)
    return _trace_registry[tid]


# ═══════════════════════════════════════════════════════════════════════════
# Node: Rewrite
# ═══════════════════════════════════════════════════════════════════════════

def rewrite_node(state: HealthGuardState) -> dict:
    """LLM-based query normalization and Input Guardrail."""
    user_input = state["user_input"]
    messages = state.get("messages", [])

    # Build history context first — needed by both the guardrail and the rewriter
    history_parts = []
    for msg in messages[:-1]:
        if hasattr(msg, "content"):
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            history_parts.append(f"{role}: {msg.content}")
    history_context = "\n".join(history_parts[-10:]) if history_parts else ""

    logger = _get_logger(state)
    is_valid, fallback_msg = query_validator(user_input, history_context)
    if not is_valid:
        logger.step("rewrite (guardrail)", input=user_input, output="FAIL", reasoning="Out of scope query")
        return {
            "rewritten_query": user_input,
            "route_decision": "FAIL_GUARDRAIL",
            "final_answer": fallback_msg,
            "trace_id": state.get("trace_id") or str(uuid.uuid4()),
            "retry_count": 0,
            "react_count": 0,
            "error_context": "",
            "current_tool": "",
            "validation_result": "PASS",
        }

    t0 = time.monotonic()
    rewritten = rewrite_query(user_input, history_context)
    dur = (time.monotonic() - t0) * 1000

    logger = _get_logger(state)
    changed = rewritten != user_input
    logger.step("rewrite",
        input=user_input,
        output=rewritten,
        reasoning=f"LLM normalized query" if changed else "No changes needed — query already well-formed",
        duration_ms=dur)

    return {
        "rewritten_query": rewritten,
        "trace_id": state.get("trace_id") or str(uuid.uuid4()),
        "retry_count": 0,
        "react_count": state.get("react_count", 0),
        "error_context": "",
        "current_tool": "",
        "validation_result": "",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Node: Route
# ═══════════════════════════════════════════════════════════════════════════

def route_node(state: HealthGuardState) -> dict:
    """Use the LLM to decide which tool(s) to route to."""
    if state.get("route_decision") == "FAIL_GUARDRAIL":
        return {}
        
    rewritten = state["rewritten_query"]
    t0 = time.monotonic()
    routing = route_query(rewritten)
    dur = (time.monotonic() - t0) * 1000

    logger = _get_logger(state)
    react_count = state.get("react_count", 0)
    logger.step("route",
        input=rewritten,
        output=routing["tool"],
        reasoning=routing["reason"],
        duration_ms=dur,
        metadata={
            "tools_list": routing["tools_list"],
            "react_iteration": react_count if react_count > 0 else None,
        })

    return {
        "route_decision": routing["tool"],
        "route_reason": routing["reason"],
        "tools_list": routing["tools_list"],
        "retry_count": 0,
        "error_context": "",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Conditional Edge: Route Dispatcher
# ═══════════════════════════════════════════════════════════════════════════

def route_dispatcher(state: HealthGuardState) -> str:
    """Dispatch to the appropriate execute node based on route_decision."""
    decision = state["route_decision"]
    if decision == "FAIL_GUARDRAIL":
        return "finalize"
    elif decision == "SQL_TOOL":
        return "execute_sql"
    elif decision == "CSV_TOOL":
        return "execute_csv"
    elif decision == "RAG_TOOL":
        return "execute_rag"
    elif decision == "MULTI_TOOL":
        return "execute_multi"
    else:
        return "execute_rag"  # fallback


# ═══════════════════════════════════════════════════════════════════════════
# Tool Execution Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _run_sql(query: str, error_context: str = "") -> dict:
    """Execute SQL tool, optionally with error context for retry."""
    if error_context:
        query = f"{query}\n\n[PREVIOUS ATTEMPT FAILED: {error_context}. Please fix the SQL.]"
    result = sql_tool(query)
    return {
        "tool": "SQL_TOOL",
        "code": result.get("sql", ""),
        "formatted": result.get("formatted", ""),
        "raw_results": result.get("raw_results", []),
        "error": result.get("error"),
    }


def _run_csv(query: str, error_context: str = "") -> dict:
    """Execute CSV tool, optionally with error context for retry."""
    if error_context:
        query = f"{query}\n\n[PREVIOUS ATTEMPT FAILED: {error_context}. Please fix the Python code.]"
    result = python_tool(query)
    return {
        "tool": "CSV_TOOL",
        "code": result.get("code", ""),
        "formatted": result.get("formatted", ""),
        "raw_results": result.get("raw_results"),
        "error": result.get("error"),
    }


def _run_rag(query: str) -> dict:
    """Execute RAG tool."""
    result = rag_tool(query)
    return {
        "tool": "RAG_TOOL",
        "code": "",
        "formatted": "",
        "context": result.get("context", ""),
        "results": result.get("results", []),
        "error": result.get("error"),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Node: Execute SQL
# ═══════════════════════════════════════════════════════════════════════════

def execute_sql_node(state: HealthGuardState) -> dict:
    """Execute SQL tool with optional error context for self-correction."""
    error_ctx = state.get("error_context", "")
    retry = state.get("retry_count", 0)
    t0 = time.monotonic()
    result = _run_sql(state["rewritten_query"], error_ctx)
    dur = (time.monotonic() - t0) * 1000

    logger = _get_logger(state)
    logger.step("execute_sql",
        input=state["rewritten_query"],
        output=result.get("formatted", "")[:500] or "(empty)",
        reasoning="SQL code generation + execution" + (f" (retry with error context)" if error_ctx else ""),
        duration_ms=dur,
        metadata={
            "tool": "SQL_TOOL",
            "code": result.get("code", ""),
            "error": result.get("error"),
            "attempt": retry + 1 if retry > 0 else None,
            "error_context_used": error_ctx or None,
        })

    return {"tool_results": [result], "current_tool": "SQL_TOOL"}


def execute_csv_node(state: HealthGuardState) -> dict:
    """Execute CSV/Python tool with optional error context for self-correction."""
    error_ctx = state.get("error_context", "")
    retry = state.get("retry_count", 0)
    t0 = time.monotonic()
    result = _run_csv(state["rewritten_query"], error_ctx)
    dur = (time.monotonic() - t0) * 1000

    logger = _get_logger(state)
    logger.step("execute_csv",
        input=state["rewritten_query"],
        output=result.get("formatted", "")[:500] or "(empty)",
        reasoning="Python code generation + execution" + (f" (retry with error context)" if error_ctx else ""),
        duration_ms=dur,
        metadata={
            "tool": "CSV_TOOL",
            "code": result.get("code", ""),
            "error": result.get("error"),
            "attempt": retry + 1 if retry > 0 else None,
            "error_context_used": error_ctx or None,
        })

    return {"tool_results": [result], "current_tool": "CSV_TOOL"}


def execute_rag_node(state: HealthGuardState) -> dict:
    """Execute hybrid RAG search. No retry needed (no code generation)."""
    t0 = time.monotonic()
    result = _run_rag(state["rewritten_query"])
    dur = (time.monotonic() - t0) * 1000

    logger = _get_logger(state)
    ctx = result.get("context", "")
    logger.step("execute_rag",
        input=state["rewritten_query"],
        output=ctx[:500] or "(no context retrieved)",
        reasoning="Hybrid RAG: ChromaDB vector search + BM25 keyword search + reranking",
        duration_ms=dur,
        metadata={
            "tool": "RAG_TOOL",
            "chunks_retrieved": len(result.get("results", [])),
            "error": result.get("error"),
        })

    return {"tool_results": [result], "current_tool": "RAG_TOOL"}


def execute_multi_node(state: HealthGuardState) -> dict:
    """Execute multiple tools sequentially. Each tool's result enriches the next query."""
    rewritten = state["rewritten_query"]
    tools_list = state["tools_list"]
    error_ctx = state.get("error_context", "")
    logger = _get_logger(state)
    t0 = time.monotonic()

    all_results = []
    enriched_query = rewritten

    for i, t in enumerate(tools_list):
        tool_t0 = time.monotonic()
        if t == "SQL_TOOL":
            result = _run_sql(enriched_query, error_ctx if i == 0 else "")
        elif t == "CSV_TOOL":
            result = _run_csv(enriched_query, error_ctx if i == 0 else "")
        elif t == "RAG_TOOL":
            result = _run_rag(enriched_query)
        else:
            result = {"tool": t, "error": f"Unknown tool: {t}"}
        tool_dur = (time.monotonic() - tool_t0) * 1000

        all_results.append(result)
        prev_output = result.get("formatted") or result.get("context") or ""

        logger.step(f"execute_multi ({t})",
            input=enriched_query[:300],
            output=prev_output[:300] or result.get("error", "(empty)"),
            reasoning=f"MULTI_TOOL sub-step {i+1}/{len(tools_list)}: {t}",
            duration_ms=tool_dur,
            metadata={
                "tool": t,
                "code": result.get("code", ""),
                "error": result.get("error"),
                "sub_step": f"{i+1}/{len(tools_list)}",
            })

        if prev_output and not result.get("error"):
            enriched_query = f"{rewritten}\n\n[Context from {t}: {prev_output[:500]}]"

    total_dur = (time.monotonic() - t0) * 1000
    return {"tool_results": all_results, "current_tool": "MULTI_TOOL"}


# ═══════════════════════════════════════════════════════════════════════════
# Node: Check Retry (self-correction loop)
# ═══════════════════════════════════════════════════════════════════════════

def check_retry_node(state: HealthGuardState) -> dict:
    """Inspect tool results for errors. Prepare retry context if needed."""
    tool_results = state.get("tool_results", [])
    retry_count = state.get("retry_count", 0)
    logger = _get_logger(state)

    errors = [r for r in tool_results if r.get("error")]

    if errors and retry_count < MAX_TOOL_RETRIES:
        error_details = "; ".join(f"[{e['tool']}] {e['error']}" for e in errors)
        decision = f"RETRY ({retry_count + 1}/{MAX_TOOL_RETRIES}) — re-executing with error context"

        logger.step("check_retry",
            input=f"{len(errors)} error(s) in tool results",
            output=f"retry_count: {retry_count} → {retry_count + 1}",
            reasoning=decision,
            metadata={"errors": error_details, "retry_count": retry_count + 1})

        return {"retry_count": retry_count + 1, "error_context": error_details}

    if errors:
        decision = f"Max retries ({MAX_TOOL_RETRIES}) exhausted — proceeding with errors"
    else:
        decision = "No errors — proceeding to synthesize"

    logger.step("check_retry",
        input=f"{len(errors)} error(s), retry_count={retry_count}",
        output="→ synthesize",
        reasoning=decision)

    return {"error_context": ""}


def retry_router(state: HealthGuardState) -> str:
    """Decide whether to retry the tool or proceed to synthesis."""
    tool_results = state.get("tool_results", [])
    retry_count = state.get("retry_count", 0)
    current_tool = state.get("current_tool", "")
    errors = [r for r in tool_results if r.get("error")]

    if errors and retry_count <= MAX_TOOL_RETRIES and state.get("error_context"):
        if current_tool == "SQL_TOOL":
            return "execute_sql"
        elif current_tool == "CSV_TOOL":
            return "execute_csv"
        elif current_tool == "MULTI_TOOL":
            return "execute_multi"
    return "synthesize"


# ═══════════════════════════════════════════════════════════════════════════
# Node: Synthesize
# ═══════════════════════════════════════════════════════════════════════════

def synthesize_node(state: HealthGuardState) -> dict:
    """Use the LLM to synthesize a final answer from tool results + history."""
    rewritten = state["rewritten_query"]
    tool_results = state.get("tool_results", [])
    messages = state.get("messages", [])

    context_parts = []
    for tr in tool_results:
        tool_name = tr["tool"]
        if tr.get("error"):
            context_parts.append(f"[{tool_name}] Error: {tr['error']}")
        else:
            output = tr.get("formatted") or tr.get("context") or ""
            code_used = tr.get("code") or tr.get("sql") or ""
            code_block = f"Executed Query/Code:\n{code_used}\n\n" if code_used else ""
            context_parts.append(f"[{tool_name}] Result:\n{code_block}{output}")
    tool_context = "\n\n".join(context_parts)
    
    history_parts = []
    for msg in messages:
        if hasattr(msg, "content"):
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            history_parts.append(f"{role}: {msg.content}")
            
    # Include history in the context we pass to guardrails so they don't reject valid follow-ups
    full_guardrail_context = tool_context
    if history_parts:
        full_guardrail_context += "\n\nConversation History:\n" + "\n".join(history_parts[-10:])

    _logger = _get_logger(state)
    is_sufficient, fallback_msg = context_validator(rewritten, full_guardrail_context)
    if not is_sufficient:
        _logger.step("synthesize (guardrail)", input=rewritten, output="FAIL", reasoning="Insufficient context from tools")
        return {"final_answer": fallback_msg}

    system_prompt = (
        "You must answer ONLY using the provided context. "
        "If the answer is not present in the context, respond with: "
        "'No relevant information found in the provided knowledge sources.' "
        "Do NOT use prior knowledge or assumptions."
    )

    llm_messages = [{"role": "system", "content": system_prompt}]

    if history_parts:
        llm_messages.append({
            "role": "system",
            "content": "Previous conversation:\n" + "\n".join(history_parts[-10:]),
        })

    llm_messages.append({
        "role": "user",
        "content": f"User question: {rewritten}\n\nTool results:\n{tool_context}\n\nPlease provide a clear answer based on these results.",
    })

    t0 = time.monotonic()
    answer = llm_completion(
        messages=llm_messages, temperature=0.3, max_tokens=1024,
    )
    dur = (time.monotonic() - t0) * 1000

    logger = _get_logger(state)
    logger.step("synthesize",
        input=f"Query: {rewritten} | {len(tool_results)} tool result(s) | {len(history_parts)} history msgs",
        output=answer[:500],
        reasoning=f"LLM synthesis from {len(tool_results)} tool result(s)",
        duration_ms=dur)

    return {"final_answer": answer}


# ═══════════════════════════════════════════════════════════════════════════
# Node: Validate (answer quality check)
# ═══════════════════════════════════════════════════════════════════════════

def validate_node(state: HealthGuardState) -> dict:
    """LLM checks if the answer fully addresses the user's question and enforces Output Guardrails."""
    user_input = state["user_input"]
    answer = state.get("final_answer", "")
    react_count = state.get("react_count", 0)
    logger = _get_logger(state)

    if answer in [FALLBACK_OUT_OF_SCOPE, FALLBACK_NO_DATA, FALLBACK_INSUFFICIENT_CONTEXT]:
        return {"validation_result": "PASS"}

    tool_results = state.get("tool_results", [])
    context_parts = []
    for tr in tool_results:
        output = tr.get("formatted") or tr.get("context") or ""
        code_used = tr.get("code") or tr.get("sql") or ""
        code_block = f"Executed Query/Code:\n{code_used}\n\n" if code_used else ""
        context_parts.append(f"[{tr['tool']}] Result:\n{code_block}{output}")
    tool_context = "\n\n".join(context_parts)
    
    messages = state.get("messages", [])
    history_parts = []
    for msg in messages:
        if hasattr(msg, "content"):
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            history_parts.append(f"{role}: {msg.content}")
            
    full_guardrail_context = tool_context
    if history_parts:
        full_guardrail_context += "\n\nConversation History:\n" + "\n".join(history_parts[-10:])

    is_grounded = response_validator(user_input, full_guardrail_context, answer)
    if not is_grounded:
        logger.step("validate (guardrail)", input=answer[:100], output="FAIL", reasoning="Response hallucinated or contained external knowledge")
        return {"final_answer": FALLBACK_INSUFFICIENT_CONTEXT, "validation_result": "PASS"}

    if react_count >= MAX_REACT_LOOPS:
        logger.step("validate",
            input=f"Question + Answer (react_count={react_count})",
            output="PASS (skipped — max ReAct loops reached)",
            reasoning=f"Skipping validation: react_count ({react_count}) >= max ({MAX_REACT_LOOPS})")
        return {"validation_result": "PASS"}

    try:
        t0 = time.monotonic()
        verdict = llm_completion(
            messages=[
                {"role": "system", "content": VALIDATOR_SYSTEM_PROMPT},
                {"role": "user", "content": f"User's question: {user_input}\n\nAssistant's answer: {answer}"},
            ],
            temperature=0, max_tokens=100,
        )
        dur = (time.monotonic() - t0) * 1000

        first_line = verdict.split("\n")[0].strip()
        reason = verdict.split("\n")[1].strip() if "\n" in verdict else ""
        next_step = "→ finalize" if "PASS" in first_line.upper() else f"→ re-route (ReAct loop {react_count + 1})"

        logger.step("validate",
            input=f"Q: {user_input[:200]} | A: {answer[:200]}",
            output=first_line,
            reasoning=reason or "No reason provided",
            duration_ms=dur,
            metadata={"verdict": first_line, "react_count": react_count, "next": next_step})

        return {"validation_result": verdict}
    except Exception as e:
        logger.step("validate",
            input=f"Q: {user_input[:200]}",
            output="PASS (fallback — LLM call failed)",
            reasoning=str(e))
        return {"validation_result": "PASS"}


def validation_router(state: HealthGuardState) -> str:
    """Route based on validation result: PASS → finalize, FAIL → re-route (ReAct)."""
    verdict = state.get("validation_result", "PASS")
    react_count = state.get("react_count", 0)
    if "FAIL" in verdict.upper() and react_count < MAX_REACT_LOOPS:
        return "re_route"
    return "finalize"


# ═══════════════════════════════════════════════════════════════════════════
# Node: ReAct re-route
# ═══════════════════════════════════════════════════════════════════════════

def react_reroute_node(state: HealthGuardState) -> dict:
    """Increment the ReAct counter and prepare for re-routing."""
    new_count = state.get("react_count", 0) + 1
    logger = _get_logger(state)
    logger.step("react_reroute",
        input=f"Validation FAILED, react_count: {new_count - 1} → {new_count}",
        output="→ route (re-attempting with different approach)",
        reasoning=f"Answer was incomplete/incorrect. Re-routing for attempt {new_count}/{MAX_REACT_LOOPS}",
        metadata={"react_count": new_count})

    return {
        "react_count": new_count,
        "retry_count": 0,
        "error_context": "",
        "tool_results": [],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Node: Finalize (flush trace + add answer to messages)
# ═══════════════════════════════════════════════════════════════════════════

def finalize_node(state: HealthGuardState) -> dict:
    """Flush trace logs to disk and add the final answer to messages."""
    answer = state.get("final_answer", "")
    trace_id = state.get("trace_id", "")

    logger = _get_logger(state)
    logger.step("finalize",
        input=f"Answer length: {len(answer)} chars",
        output="✅ Trace flushed to disk",
        reasoning=f"Total steps: {logger._step_counter + 1}",
        metadata={
            "retry_count": state.get("retry_count", 0),
            "react_count": state.get("react_count", 0),
            "route_decision": state.get("route_decision", ""),
        })

    logger.flush()
    trace_markdown = logger.get_markdown_report()

    # Clean up registry
    _trace_registry.pop(trace_id, None)

    return {
        "trace_markdown": trace_markdown,
        "messages": [AIMessage(content=answer)],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Build the Agentic StateGraph
# ═══════════════════════════════════════════════════════════════════════════

def _build_graph() -> StateGraph:
    """Construct the fully agentic HealthGuard StateGraph."""
    builder = StateGraph(HealthGuardState)

    # ── Add all nodes ──
    builder.add_node("rewrite", rewrite_node)
    builder.add_node("route", route_node)
    builder.add_node("execute_sql", execute_sql_node)
    builder.add_node("execute_csv", execute_csv_node)
    builder.add_node("execute_rag", execute_rag_node)
    builder.add_node("execute_multi", execute_multi_node)
    builder.add_node("check_retry", check_retry_node)
    builder.add_node("synthesize", synthesize_node)
    builder.add_node("validate", validate_node)
    builder.add_node("react_reroute", react_reroute_node)
    builder.add_node("finalize", finalize_node)

    # ── Edge: START → rewrite → route ──
    builder.add_edge(START, "rewrite")
    builder.add_edge("rewrite", "route")

    # ── Conditional Edge: route → execute_* (conditional routing) ──
    builder.add_conditional_edges(
        "route",
        route_dispatcher,
        {
            "execute_sql": "execute_sql",
            "execute_csv": "execute_csv",
            "execute_rag": "execute_rag",
            "execute_multi": "execute_multi",
            "finalize": "finalize",
        },
    )

    # ── All execute nodes → check_retry ──
    builder.add_edge("execute_sql", "check_retry")
    builder.add_edge("execute_csv", "check_retry")
    builder.add_edge("execute_rag", "check_retry")
    builder.add_edge("execute_multi", "check_retry")

    # ── Conditional Edge: check_retry → retry or synthesize ──
    builder.add_conditional_edges(
        "check_retry",
        retry_router,
        {
            "execute_sql": "execute_sql",
            "execute_csv": "execute_csv",
            "execute_multi": "execute_multi",
            "synthesize": "synthesize",
        },
    )

    # ── synthesize → validate ──
    builder.add_edge("synthesize", "validate")

    # ── Conditional Edge: validate → finalize or ReAct re-route ──
    builder.add_conditional_edges(
        "validate",
        validation_router,
        {
            "finalize": "finalize",
            "re_route": "react_reroute",
        },
    )

    # ── ReAct re-route → route (loop back) ──
    builder.add_edge("react_reroute", "route")

    # ── finalize → END ──
    builder.add_edge("finalize", END)

    return builder


# ═══════════════════════════════════════════════════════════════════════════
# Compiled graph with SqliteSaver checkpointer
# ═══════════════════════════════════════════════════════════════════════════

# SqliteSaver for conversation persistence
_conn = _sqlite3.connect(str(CHECKPOINT_DB_PATH), check_same_thread=False)
_checkpointer = SqliteSaver(_conn)

# Build and compile the graph
_builder = _build_graph()
graph = _builder.compile(checkpointer=_checkpointer)


# ═══════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════

def process_query(user_input: str, session_id: str) -> dict:
    """
    Run the agentic LangGraph pipeline for a user query.

    Features:
    - Conditional routing to dedicated tool nodes
    - Self-correction retry loop (max 2) for failed tool executions
    - Answer validation with ReAct re-routing (max 2 loops)
    - Automatic memory persistence via SqliteSaver checkpointer

    Returns:
        dict with keys: session_id, trace_id, answer, tools_used, trace_markdown
    """
    # Ensure RAG index is ready (lazy init, cached after first call)
    try:
        index_documents()
    except Exception:
        pass  # Non-fatal; RAG may still work from cache

    trace_id = str(uuid.uuid4())

    # LangGraph config — thread_id enables checkpointer persistence
    config = {"configurable": {"thread_id": session_id}}

    # Input state
    input_state = {
        "user_input": user_input,
        "session_id": session_id,
        "trace_id": trace_id,
        "messages": [HumanMessage(content=user_input)],
        "rewritten_query": "",
        "route_decision": "",
        "route_reason": "",
        "tools_list": [],
        "tool_results": [],
        "final_answer": "",
        "trace_markdown": "",
        "retry_count": 0,
        "current_tool": "",
        "react_count": 0,
        "validation_result": "",
        "error_context": "",
    }

    # Invoke the graph
    result = graph.invoke(input_state, config)

    return {
        "session_id": session_id,
        "trace_id": result.get("trace_id", trace_id),
        "answer": result.get("final_answer", ""),
        "tools_used": result.get("tools_list", []),
        "trace_markdown": result.get("trace_markdown", ""),
        "retry_count": result.get("retry_count", 0),
        "react_count": result.get("react_count", 0),
        "validation_result": result.get("validation_result", ""),
    }


async def astream_query(user_input: str, session_id: str):
    """
    Async generator that streams LangGraph events via astream_events.

    Yields dicts with event info as each node starts/completes.
    Used by the SSE streaming endpoint.
    """
    try:
        index_documents()
    except Exception:
        pass

    trace_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    input_state = {
        "user_input": user_input,
        "session_id": session_id,
        "trace_id": trace_id,
        "messages": [HumanMessage(content=user_input)],
        "rewritten_query": "",
        "route_decision": "",
        "route_reason": "",
        "tools_list": [],
        "tool_results": [],
        "final_answer": "",
        "trace_markdown": "",
        "retry_count": 0,
        "current_tool": "",
        "react_count": 0,
        "validation_result": "",
        "error_context": "",
    }

    async for event in graph.astream_events(input_state, config, version="v2"):
        kind = event.get("event", "")
        name = event.get("name", "")

        if kind == "on_chain_start" and name in (
            "rewrite", "route", "execute_sql", "execute_csv",
            "execute_rag", "execute_multi", "check_retry",
            "synthesize", "validate", "finalize",
        ):
            yield {"event": "node_start", "node": name}

        elif kind == "on_chain_end" and name == "finalize":
            output = event.get("data", {}).get("output", {})
            yield {
                "event": "final_answer",
                "answer": output.get("final_answer", ""),
                "trace_markdown": output.get("trace_markdown", ""),
            }


def get_thread_history(session_id: str) -> list[dict]:
    """
    Retrieve conversation history for a session from the LangGraph checkpointer.

    Returns list of dicts with 'role' and 'content' keys.
    """
    config = {"configurable": {"thread_id": session_id}}
    try:
        state = graph.get_state(config)
        if state and state.values and "messages" in state.values:
            history = []
            for msg in state.values["messages"]:
                if isinstance(msg, HumanMessage):
                    history.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    history.append({"role": "assistant", "content": msg.content})
            return history
    except Exception:
        pass
    return []


def clear_thread_history(session_id: str) -> None:
    """Clear conversation history for a session."""
    config = {"configurable": {"thread_id": session_id}}
    try:
        pass  # LangGraph checkpointers don't natively support deletion
    except Exception:
        pass
