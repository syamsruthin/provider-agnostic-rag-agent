"""
Orchestrator — The main agent pipeline
========================================
Ties together: Rewrite → Route → Execute → Synthesize
with full tracing and memory support.
"""

import uuid

from groq import Groq

from backend.agents.router import rewrite_query, route_query
from backend.agents.sql_agent import sql_tool
from backend.agents.csv_agent import python_tool
from backend.agents.rag_agent import rag_tool, index_documents
from backend.core.config import GROQ_API_KEY, GROQ_MODEL
from backend.core.logger import TraceLogger
from backend.core.memory import memory


def _get_groq_client() -> Groq:
    return Groq(api_key=GROQ_API_KEY)


def _synthesize(user_query: str, tool_results: list[dict], context_history: str = "") -> str:
    """
    Use the LLM to synthesize a final human-readable answer from tool results.
    """
    # Build context from tool results
    context_parts = []
    for tr in tool_results:
        tool_name = tr["tool"]
        if tr.get("error"):
            context_parts.append(f"[{tool_name}] Error: {tr['error']}")
        else:
            output = tr.get("formatted") or tr.get("context") or ""
            context_parts.append(f"[{tool_name}] Result:\n{output}")

    tool_context = "\n\n".join(context_parts)

    system_prompt = (
        "You are a helpful health insurance assistant for HealthGuard Insurance. "
        "You have been given the results from various data tools. "
        "Synthesize a clear, accurate, and helpful answer to the user's question. "
        "Use the tool results as your source of truth. "
        "If results are empty or tools returned errors, acknowledge that honestly. "
        "Format your answer in a readable way. Use bullet points or tables where appropriate."
    )

    messages = [
        {"role": "system", "content": system_prompt},
    ]

    # Add conversation history for continuity
    if context_history:
        messages.append({
            "role": "system",
            "content": f"Previous conversation:\n{context_history}",
        })

    messages.append({
        "role": "user",
        "content": (
            f"User question: {user_query}\n\n"
            f"Tool results:\n{tool_context}\n\n"
            "Please provide a clear answer based on these results."
        ),
    })

    client = _get_groq_client()
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=1024,
    )
    return response.choices[0].message.content.strip()


def _execute_tool(tool_name: str, query: str) -> dict:
    """Execute a single tool and return standardized results."""
    if tool_name == "SQL_TOOL":
        result = sql_tool(query)
        return {
            "tool": "SQL_TOOL",
            "code": result.get("sql", ""),
            "formatted": result.get("formatted", ""),
            "raw_results": result.get("raw_results", []),
            "error": result.get("error"),
        }
    elif tool_name == "CSV_TOOL":
        result = python_tool(query)
        return {
            "tool": "CSV_TOOL",
            "code": result.get("code", ""),
            "formatted": result.get("formatted", ""),
            "raw_results": result.get("raw_results"),
            "error": result.get("error"),
        }
    elif tool_name == "RAG_TOOL":
        result = rag_tool(query)
        return {
            "tool": "RAG_TOOL",
            "code": "",
            "formatted": "",
            "context": result.get("context", ""),
            "results": result.get("results", []),
            "error": result.get("error"),
        }
    else:
        return {"tool": tool_name, "error": f"Unknown tool: {tool_name}"}


def process_query(user_input: str, session_id: str) -> dict:
    """
    Main orchestration pipeline:
    1. Rewrite query (de-alias states, normalize terms)
    2. Route to tool(s) via LLM
    3. Execute tool(s)
    4. Synthesize final answer
    5. Log trace (JSONL + Markdown)
    6. Store in memory

    Returns:
        dict with keys: session_id, trace_id, answer, tools_used, trace_markdown
    """
    trace_id = str(uuid.uuid4())
    logger = TraceLogger(trace_id=trace_id, session_id=session_id)

    # Ensure RAG index is ready (lazy init, cached after first call)
    try:
        index_documents()
    except Exception:
        pass  # Non-fatal; RAG may still work from cache

    # --- Step 1: Query Rewrite ---
    rewritten = rewrite_query(user_input)
    logger.set_user_query(user_input)
    logger.set_rewrite(rewritten)
    logger.log("QueryRewriter", input=user_input, output=rewritten,
               reasoning="De-aliased state names and medical terms")

    # --- Step 2: Route ---
    routing = route_query(rewritten)
    tool_choice = routing["tool"]
    reason = routing["reason"]
    tools_list = routing["tools_list"]

    logger.set_router_decision(tool_choice, reason)
    logger.log("Router", input=rewritten, output=tool_choice,
               reasoning=reason, tools_list=tools_list)

    # --- Step 3: Execute tool(s) ---
    tool_results = []
    for t in tools_list:
        result = _execute_tool(t, rewritten)
        tool_results.append(result)

        # Log each tool execution
        logger.set_tool_execution(
            tool_name=t,
            code=result.get("code", ""),
            result=result.get("formatted", result.get("context", "")),
            error=result.get("error", ""),
        )
        logger.log(
            f"ToolExecution:{t}",
            input=rewritten,
            output=result.get("formatted", result.get("context", ""))[:500],
            code=result.get("code", ""),
            error=result.get("error"),
        )

    # --- Step 4: Synthesize ---
    context_history = memory.get_context_string(session_id)
    answer = _synthesize(rewritten, tool_results, context_history)

    logger.set_synthesis(answer)
    logger.log("Synthesizer", input=f"Query: {rewritten}", output=answer[:500])

    # --- Step 5: Write logs ---
    logger.flush()
    trace_markdown = logger.get_markdown_report()

    # --- Step 6: Store in memory ---
    memory.add(session_id, user=user_input, assistant=answer)

    return {
        "session_id": session_id,
        "trace_id": trace_id,
        "answer": answer,
        "tools_used": tools_list,
        "trace_markdown": trace_markdown,
    }
