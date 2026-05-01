"""
Python/CSV Tool — Natural Language → Python Code → Pandas Execution → Results
==============================================================================
Takes a natural-language question about providers, uses Groq/LLama-3 to
generate pandas code, executes it in a sandboxed namespace against the
providers.csv DataFrame, and returns the results.
"""

import pandas as pd
from groq import Groq

from backend.core.config import CSV_PATH, GROQ_API_KEY, GROQ_MODEL, CSV_SYSTEM_PROMPT


def _get_groq_client() -> Groq:
    """Return a Groq client instance."""
    return Groq(api_key=GROQ_API_KEY)


def _load_dataframe() -> pd.DataFrame:
    """Load providers.csv into a pandas DataFrame with proper types."""
    df = pd.read_csv(str(CSV_PATH))
    # Ensure boolean column is properly typed
    if "is_accepting_new_patients" in df.columns:
        df["is_accepting_new_patients"] = df["is_accepting_new_patients"].map(
            {"True": True, "False": False, True: True, False: False}
        )
    # Ensure zip_code is string to preserve leading zeros
    if "zip_code" in df.columns:
        df["zip_code"] = df["zip_code"].astype(str)
    return df


def _generate_python_code(user_query: str) -> str:
    """Use Groq LLama-3 to generate pandas code from natural language."""
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": CSV_SYSTEM_PROMPT},
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


def _execute_python(code: str, df: pd.DataFrame) -> object:
    """
    Execute LLM-generated pandas code in a restricted namespace.
    The code must assign to a variable called `result`.
    """
    # Sandboxed namespace with only pandas and the DataFrame
    namespace = {"df": df, "pd": pd}
    try:
        exec(code, {"__builtins__": {}}, namespace)
    except Exception as e:
        raise RuntimeError(f"Python execution error: {e}\nCode:\n{code}") from e

    if "result" not in namespace:
        raise RuntimeError(
            f"Generated code did not produce a 'result' variable.\nCode:\n{code}"
        )

    return namespace["result"]


def _format_results(result: object) -> str:
    """Format the execution result into a readable string."""
    if isinstance(result, pd.DataFrame):
        if result.empty:
            return "No matching providers found."
        return result.to_string(index=False)
    elif isinstance(result, pd.Series):
        return result.to_string()
    else:
        return str(result)


def python_tool(user_query: str) -> dict:
    """
    End-to-end Python/CSV tool: NL → Python code → Execute → Results.

    Returns:
        dict with keys:
            - code: the generated Python code
            - raw_results: the result object (DataFrame, Series, or scalar)
            - formatted: human-readable string of results
            - error: error message if any, else None
    """
    code = ""
    try:
        df = _load_dataframe()
        code = _generate_python_code(user_query)
        result = _execute_python(code, df)
        formatted = _format_results(result)
        return {
            "code": code,
            "raw_results": result,
            "formatted": formatted,
            "error": None,
        }
    except Exception as e:
        return {
            "code": code,
            "raw_results": None,
            "formatted": "",
            "error": str(e),
        }
