"""
SQL Agent — Thin wrapper over SQLExecutionEngine for plan_benefits.
====================================================================
Instantiates the engine with the plan_benefits data source config.
The engine itself is reusable for any SQLite database.
"""

from backend.core.tools import SQLExecutionEngine
from backend.core.data_sources import PLAN_BENEFITS_SOURCE

# Instantiate the engine with the plan_benefits config
_engine = SQLExecutionEngine(
    db_path=PLAN_BENEFITS_SOURCE["db_path"],
    system_prompt=PLAN_BENEFITS_SOURCE["system_prompt"],
)


def sql_tool(user_query: str) -> dict:
    """
    Query the plan_benefits table using natural language.

    Returns dict with keys: sql, raw_results, formatted, error
    """
    return _engine.run(user_query)
