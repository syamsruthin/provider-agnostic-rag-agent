"""
Router Agent — LLM Query Rewrite + LLM-based Tool Routing
============================================================
1. Rewrites the user query via LLM (normalizes terms, de-aliases, clarifies).
2. Routes to the appropriate tool(s) via the configured LLM provider.
3. Returns routing decision with reasoning.
"""

import json

from backend.core.llm import llm_completion
from backend.core.config import ROUTER_SYSTEM_PROMPT, REWRITER_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Query Re-writer: LLM-based normalization
# ---------------------------------------------------------------------------

def rewrite_query(query: str, history_context: str = "") -> str:
    """
    Use the LLM to rewrite/normalize the user query:
    - Contextualize pronouns ('those', 'it') using history_context.
    - Replace full US state names with 2-letter abbreviations.
    - Replace colloquial medical terms with exact specialty names
      (e.g., "heart doctor" → "Cardiologist").
    - Fix typos, expand abbreviations, and clarify ambiguous phrasing.
    - Preserve the original intent — do NOT answer the question.

    Returns the rewritten query string.
    Falls back to the original query if the LLM call fails.
    """
    try:
        user_content = query
        if history_context:
            user_content = f"CONVERSATION HISTORY:\n{history_context}\n\nCURRENT QUERY: {query}"

        rewritten = llm_completion(
            messages=[
                {"role": "system", "content": REWRITER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0,
            max_tokens=256,
        )
        # Guard: if the LLM returns an empty string, fall back
        return rewritten if rewritten else query
    except Exception:
        # On any LLM failure, return the original query unchanged
        return query


# ---------------------------------------------------------------------------
# Router: LLM-based tool selection
# ---------------------------------------------------------------------------
VALID_TOOLS = {"SQL_TOOL", "CSV_TOOL", "RAG_TOOL", "MULTI_TOOL"}


def route_query(user_query: str) -> dict:
    """
    Use the LLM to decide which tool(s) to route the query to.

    Returns:
        dict with keys:
            - tool: one of SQL_TOOL, CSV_TOOL, RAG_TOOL, MULTI_TOOL
            - reason: explanation of why this tool was chosen
            - tools_list: for MULTI_TOOL, list of individual tools to invoke
            - error: error message if routing failed
    """
    raw = llm_completion(
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ],
        temperature=0,
        max_tokens=256,
    )

    # Parse JSON response
    try:
        # Strip any markdown fences
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw = "\n".join(lines).strip()

        decision = json.loads(raw)
        tool = decision.get("tool", "").upper()
        reason = decision.get("reason", "No reason provided.")

        if tool not in VALID_TOOLS:
            # Fallback: try to infer from the response
            return {
                "tool": "RAG_TOOL",
                "reason": f"Could not parse tool '{tool}', defaulting to RAG. Original: {reason}",
                "tools_list": ["RAG_TOOL"],
                "error": None,
            }

        # For MULTI_TOOL, determine which sub-tools to invoke
        tools_list = []
        if tool == "MULTI_TOOL":
            reason_lower = reason.lower()
            if any(w in reason_lower for w in ["sql", "plan", "premium", "deductible", "copay", "cost"]):
                tools_list.append("SQL_TOOL")
            if any(w in reason_lower for w in ["csv", "doctor", "provider", "specialist", "location", "city"]):
                tools_list.append("CSV_TOOL")
            if any(w in reason_lower for w in ["rag", "policy", "exclusion", "right", "claim", "rule"]):
                tools_list.append("RAG_TOOL")
            # If we couldn't infer, use all
            if not tools_list:
                tools_list = ["SQL_TOOL", "CSV_TOOL"]
        else:
            tools_list = [tool]

        return {
            "tool": tool,
            "reason": reason,
            "tools_list": tools_list,
            "error": None,
        }

    except json.JSONDecodeError:
        # LLM didn't return valid JSON — try to extract intent
        return {
            "tool": "RAG_TOOL",
            "reason": f"Failed to parse LLM routing response. Raw: {raw[:200]}",
            "tools_list": ["RAG_TOOL"],
            "error": f"Invalid JSON from router: {raw[:200]}",
        }
