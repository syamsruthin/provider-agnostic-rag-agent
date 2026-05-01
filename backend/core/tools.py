"""
Execution Engines — Data-Source-Agnostic SQL & Python Executors
================================================================
Reusable engines that can be pointed at any SQLite database or any
CSV/DataFrame. The data-source-specific details (schema, prompts,
paths) are injected at instantiation time.
"""

import sqlite3
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from groq import Groq

from backend.core.config import GROQ_API_KEY, GROQ_MODEL


# ---------------------------------------------------------------------------
# Shared LLM helper
# ---------------------------------------------------------------------------
def _get_groq_client() -> Groq:
    """Return a Groq client instance."""
    return Groq(api_key=GROQ_API_KEY)


def _strip_code_fences(raw: str) -> str:
    """Remove markdown code fences that LLMs sometimes add despite prompts."""
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()
    return raw


def _generate_code(system_prompt: str, user_query: str) -> str:
    """Send a system+user prompt to Groq and return the cleaned response."""
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ],
        temperature=0,
        max_tokens=512,
    )
    return _strip_code_fences(response.choices[0].message.content.strip())


# ═══════════════════════════════════════════════════════════════════════════
# SQL Execution Engine
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class SQLExecutionEngine:
    """
    A reusable engine for NL → SQL → SQLite execution.

    Usage:
        engine = SQLExecutionEngine(
            db_path="/path/to/any.db",
            system_prompt="You are a SQL expert. Table `orders` has columns [...]",
        )
        result = engine.run("How many orders were placed last month?")
    """

    db_path: str
    system_prompt: str

    def generate_sql(self, user_query: str) -> str:
        """Generate SQL from natural language using the configured prompt."""
        return _generate_code(self.system_prompt, user_query)

    def execute_sql(self, sql: str) -> list[dict]:
        """Execute SQL against the configured database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            raise RuntimeError(f"SQL execution error: {e}\nSQL: {sql}") from e
        finally:
            conn.close()

    @staticmethod
    def format_results(results: list[dict]) -> str:
        """Format query results into a readable table string."""
        if not results:
            return "No results found."

        if len(results) == 1 and len(results[0]) == 1:
            return str(list(results[0].values())[0])

        headers = list(results[0].keys())
        lines = [" | ".join(headers), "-" * (sum(len(h) for h in headers) + 3 * (len(headers) - 1))]
        for row in results:
            lines.append(" | ".join(str(row.get(h, "")) for h in headers))
        return "\n".join(lines)

    def run(self, user_query: str) -> dict:
        """
        End-to-end: NL → SQL → Execute → Results.

        Returns dict with keys: sql, raw_results, formatted, error
        """
        sql = ""
        try:
            sql = self.generate_sql(user_query)
            results = self.execute_sql(sql)
            formatted = self.format_results(results)
            return {
                "sql": sql,
                "raw_results": results,
                "formatted": formatted,
                "error": None,
            }
        except Exception as e:
            return {
                "sql": sql,
                "raw_results": [],
                "formatted": "",
                "error": str(e),
            }


# ═══════════════════════════════════════════════════════════════════════════
# Python Execution Engine
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class PythonExecutionEngine:
    """
    A reusable engine for NL → Python/pandas code → sandboxed execution.

    Usage:
        engine = PythonExecutionEngine(
            csv_path="/path/to/any.csv",
            system_prompt="You are a Data Analyst. DataFrame `df` has columns [...]",
        )
        result = engine.run("Find all rows where city is Seattle")

    Or with an existing DataFrame:
        engine = PythonExecutionEngine(
            system_prompt="...",
            preloaded_df=my_dataframe,
        )
    """

    system_prompt: str
    csv_path: str | None = None
    preloaded_df: Any = None  # pd.DataFrame, but Any to avoid import at class level
    result_variable: str = "result"
    allowed_modules: dict = field(default_factory=lambda: {"pd": pd})
    type_coercions: dict = field(default_factory=dict)

    def load_dataframe(self) -> pd.DataFrame:
        """Load the DataFrame from CSV or return the preloaded one."""
        if self.preloaded_df is not None:
            return self.preloaded_df

        if self.csv_path is None:
            raise ValueError("Either csv_path or preloaded_df must be provided.")

        df = pd.read_csv(self.csv_path)

        # Apply any configured type coercions
        for col, coercion in self.type_coercions.items():
            if col in df.columns:
                if coercion == "bool":
                    df[col] = df[col].map(
                        {"True": True, "False": False, True: True, False: False}
                    )
                elif coercion == "str":
                    df[col] = df[col].astype(str)
                elif coercion == "int":
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                elif coercion == "float":
                    df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def generate_code(self, user_query: str) -> str:
        """Generate Python code from natural language using the configured prompt."""
        return _generate_code(self.system_prompt, user_query)

    def execute_code(self, code: str, df: pd.DataFrame) -> Any:
        """Execute LLM-generated code in a sandboxed namespace."""
        namespace = {"df": df, **self.allowed_modules}
        try:
            exec(code, {"__builtins__": {}}, namespace)
        except Exception as e:
            raise RuntimeError(f"Python execution error: {e}\nCode:\n{code}") from e

        if self.result_variable not in namespace:
            raise RuntimeError(
                f"Generated code did not produce a '{self.result_variable}' variable.\n"
                f"Code:\n{code}"
            )
        return namespace[self.result_variable]

    @staticmethod
    def format_results(result: Any) -> str:
        """Format the execution result into a readable string."""
        if isinstance(result, pd.DataFrame):
            if result.empty:
                return "No matching results found."
            return result.to_string(index=False)
        elif isinstance(result, pd.Series):
            return result.to_string()
        return str(result)

    def run(self, user_query: str) -> dict:
        """
        End-to-end: NL → Python code → Execute → Results.

        Returns dict with keys: code, raw_results, formatted, error
        """
        code = ""
        try:
            df = self.load_dataframe()
            code = self.generate_code(user_query)
            result = self.execute_code(code, df)
            formatted = self.format_results(result)
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
