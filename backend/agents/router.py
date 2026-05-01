"""
Router Agent — Query Rewrite + LLM-based Tool Routing
=======================================================
1. Rewrites the user query (de-aliases state names, normalizes terms).
2. Routes to the appropriate tool(s) via Groq LLM.
3. Returns routing decision with reasoning.
"""

import json
import re

from groq import Groq

from backend.core.config import GROQ_API_KEY, GROQ_MODEL, ROUTER_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Query Re-writer: de-alias state names, normalize medical terms
# ---------------------------------------------------------------------------
STATE_ALIASES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}

TERM_ALIASES = {
    "primary care": "PCP",
    "primary care physician": "PCP",
    "family doctor": "PCP",
    "general practitioner": "PCP",
    "heart doctor": "Cardiologist",
    "skin doctor": "Dermatologist",
    "bone doctor": "Orthopedic Surgeon",
    "brain doctor": "Neurologist",
    "eye doctor": "Ophthalmologist",
    "children's doctor": "Pediatrician",
    "child doctor": "Pediatrician",
    "stomach doctor": "Gastroenterologist",
    "lung doctor": "Pulmonologist",
    "ear nose throat": "ENT Specialist",
    "ent": "ENT Specialist",
}


def rewrite_query(query: str) -> str:
    """
    De-alias the user query:
    - Replace full state names with 2-letter abbreviations.
    - Replace colloquial medical terms with exact specialty names.
    Returns the rewritten query.
    """
    rewritten = query

    # Replace state names (case-insensitive, whole-word boundaries)
    for full_name, abbrev in STATE_ALIASES.items():
        pattern = re.compile(r"\b" + re.escape(full_name) + r"\b", re.IGNORECASE)
        rewritten = pattern.sub(abbrev, rewritten)

    # Replace medical term aliases (case-insensitive)
    for alias, canonical in TERM_ALIASES.items():
        pattern = re.compile(r"\b" + re.escape(alias) + r"\b", re.IGNORECASE)
        rewritten = pattern.sub(canonical, rewritten)

    return rewritten


# ---------------------------------------------------------------------------
# Router: LLM-based tool selection
# ---------------------------------------------------------------------------
VALID_TOOLS = {"SQL_TOOL", "CSV_TOOL", "RAG_TOOL", "MULTI_TOOL"}


def _get_groq_client() -> Groq:
    return Groq(api_key=GROQ_API_KEY)


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
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ],
        temperature=0,
        max_tokens=256,
    )
    raw = response.choices[0].message.content.strip()

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
