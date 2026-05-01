"""
CSV/Python Agent — Thin wrapper over PythonExecutionEngine for providers.
=========================================================================
Instantiates the engine with the providers data source config.
The engine itself is reusable for any CSV/DataFrame.
"""

from backend.core.tools import PythonExecutionEngine
from backend.core.data_sources import PROVIDERS_SOURCE

# Instantiate the engine with the providers config
_engine = PythonExecutionEngine(
    csv_path=PROVIDERS_SOURCE["csv_path"],
    system_prompt=PROVIDERS_SOURCE["system_prompt"],
    type_coercions=PROVIDERS_SOURCE.get("type_coercions", {}),
)


def python_tool(user_query: str) -> dict:
    """
    Query the providers CSV using natural language.

    Returns dict with keys: code, raw_results, formatted, error
    """
    return _engine.run(user_query)
