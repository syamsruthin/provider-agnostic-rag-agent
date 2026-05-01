"""
SQL Tool — Natural Language → SQL → SQLite Execution → Results
==============================================================
Takes a natural-language question about insurance plans, uses Groq/LLama-3
to generate valid SQLite SQL, executes it against insurance.db, and returns
the results as a formatted string.
"""

import sqlite3
from groq import Groq

from backend.core.config import DB_PATH, GROQ_API_KEY, GROQ_MODEL, SQL_SYSTEM_PROMPT


def _get_groq_client() -> Groq:
    """Return a Groq client instance."""
    return Groq(api_key=GROQ_API_KEY)


def _generate_sql(user_query: str) -> str:
    """Use Groq LLama-3 to generate a SQL query from natural language."""
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SQL_SYSTEM_PROMPT},
            {"role": "user", "content": user_query},
        ],
        temperature=0,
        max_tokens=512,
    )
    raw = response.choices[0].message.content.strip()

    # Strip any markdown code fences the LLM might add despite the prompt
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    return raw


def _execute_sql(sql: str) -> list[dict]:
    """Execute SQL against insurance.db and return results as list of dicts."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        # Convert sqlite3.Row objects to plain dicts
        results = [dict(row) for row in rows]
        return results
    except Exception as e:
        raise RuntimeError(f"SQL execution error: {e}\nSQL: {sql}") from e
    finally:
        conn.close()


def _format_results(results: list[dict]) -> str:
    """Format query results into a readable string."""
    if not results:
        return "No results found."

    # If only one row and one column, return the scalar value
    if len(results) == 1 and len(results[0]) == 1:
        val = list(results[0].values())[0]
        return str(val)

    # Build a readable table-like output
    lines = []
    headers = list(results[0].keys())
    lines.append(" | ".join(headers))
    lines.append("-" * len(lines[0]))
    for row in results:
        lines.append(" | ".join(str(row.get(h, "")) for h in headers))

    return "\n".join(lines)


def sql_tool(user_query: str) -> dict:
    """
    End-to-end SQL tool: NL → SQL → Execute → Formatted results.

    Returns:
        dict with keys:
            - sql: the generated SQL string
            - raw_results: list of dicts from the query
            - formatted: human-readable string of results
            - error: error message if any, else None
    """
    try:
        sql = _generate_sql(user_query)
        results = _execute_sql(sql)
        formatted = _format_results(results)
        return {
            "sql": sql,
            "raw_results": results,
            "formatted": formatted,
            "error": None,
        }
    except Exception as e:
        return {
            "sql": sql if "sql" in dir() else "",
            "raw_results": [],
            "formatted": "",
            "error": str(e),
        }
