"""
Trace Logger — JSONL machine logs + Markdown human-readable reports
====================================================================
Every agent interaction gets a trace_id. The logger writes:
1. Structured JSONL entries (one per component step) for machine auditing.
2. A Markdown report per session/trace for human review in the UI sidebar.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.core.config import LOGS_DIR


class TraceLogger:
    """
    Per-trace logger that accumulates steps and writes both JSONL and Markdown.

    Usage:
        logger = TraceLogger(trace_id="abc-123", session_id="sess-456")
        logger.log("Router", input="user query", output="SQL_TOOL", reasoning="...")
        logger.log("SQLAgent", input="...", output="...", code="SELECT ...")
        logger.set_user_query("What plans have low deductibles?")
        logger.set_rewrite("What plans have deductibles < $1000?")
        logger.set_router_decision("SQL_TOOL", "Query is about plan costs")
        logger.set_tool_execution("SQL_TOOL", code="SELECT ...", result="...")
        logger.set_synthesis("Based on the query results...")
        logger.flush()  # writes both files
    """

    def __init__(self, trace_id: str, session_id: str):
        self.trace_id = trace_id
        self.session_id = session_id
        self._entries: list[dict] = []

        # Markdown report sections
        self._user_query: str = ""
        self._rewrite: str = ""
        self._router_decision: str = ""
        self._router_reason: str = ""
        self._tool_executions: list[dict] = []
        self._synthesis: str = ""

        # Ensure logs dir exists
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------
    # Structured JSONL logging
    # -----------------------------------------------------------------
    def log(self, component: str, **kwargs) -> None:
        """
        Append a structured log entry for the given component.
        kwargs can include: input, output, reasoning, code, error, etc.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "component": component,
            **kwargs,
        }
        self._entries.append(entry)

    # -----------------------------------------------------------------
    # Markdown report builders
    # -----------------------------------------------------------------
    def set_user_query(self, query: str) -> None:
        self._user_query = query

    def set_rewrite(self, rewritten: str) -> None:
        self._rewrite = rewritten

    def set_router_decision(self, tool: str, reason: str) -> None:
        self._router_decision = tool
        self._router_reason = reason

    def set_tool_execution(self, tool_name: str, code: str = "", result: str = "", error: str = "") -> None:
        self._tool_executions.append({
            "tool": tool_name,
            "code": code,
            "result": result,
            "error": error,
        })

    def set_synthesis(self, synthesis: str) -> None:
        self._synthesis = synthesis

    # -----------------------------------------------------------------
    # Flush to disk
    # -----------------------------------------------------------------
    def flush(self) -> tuple[Path, Path]:
        """Write JSONL and Markdown files. Returns (jsonl_path, md_path)."""
        jsonl_path = self._write_jsonl()
        md_path = self._write_markdown()
        return jsonl_path, md_path

    def _write_jsonl(self) -> Path:
        """Append all log entries to the session JSONL file."""
        jsonl_path = LOGS_DIR / f"{self.session_id}.jsonl"
        with open(jsonl_path, "a") as f:
            for entry in self._entries:
                f.write(json.dumps(entry, default=str) + "\n")
        return jsonl_path

    def _write_markdown(self) -> Path:
        """Write the human-readable Markdown trace report."""
        md_path = LOGS_DIR / f"trace_{self.trace_id[:8]}.md"
        lines = [
            f"# Trace Report: `{self.trace_id[:8]}...`",
            f"**Session**: `{self.session_id[:8]}...`  ",
            f"**Timestamp**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "",
            "---",
            "",
        ]

        # Step 0: User Query
        lines.append("## User Query")
        lines.append(f"> {self._user_query}" if self._user_query else "> *(not set)*")
        lines.append("")

        # Step 1: Rewrite
        lines.append("## Step 1: Query Rewrite")
        if self._rewrite and self._rewrite != self._user_query:
            lines.append(f"**Original**: {self._user_query}  ")
            lines.append(f"**Rewritten**: {self._rewrite}")
        else:
            lines.append("*No rewrite needed — query used as-is.*")
        lines.append("")

        # Step 2: Router Decision
        lines.append("## Step 2: Router Decision")
        lines.append(f"**Tool Selected**: `{self._router_decision}`  ")
        lines.append(f"**Reasoning**: {self._router_reason}")
        lines.append("")

        # Step 3: Tool Execution(s)
        lines.append("## Step 3: Tool Execution")
        if self._tool_executions:
            for i, tex in enumerate(self._tool_executions, 1):
                lines.append(f"### {i}. {tex['tool']}")
                if tex["code"]:
                    lines.append("**Generated Code/SQL**:")
                    lines.append(f"```\n{tex['code']}\n```")
                if tex["result"]:
                    result_preview = tex["result"][:1000]
                    lines.append("**Result**:")
                    lines.append(f"```\n{result_preview}\n```")
                if tex["error"]:
                    lines.append(f"**Error**: ⚠️ {tex['error']}")
                lines.append("")
        else:
            lines.append("*No tool execution recorded.*")
            lines.append("")

        # Step 4: Synthesis
        lines.append("## Step 4: Final Synthesis")
        lines.append(self._synthesis if self._synthesis else "*No synthesis recorded.*")
        lines.append("")

        md_content = "\n".join(lines)
        md_path.write_text(md_content)
        return md_path

    def get_markdown_report(self) -> str:
        """Return the Markdown report as a string (for API response), without writing to disk."""
        # Build in-memory and return
        lines = []
        lines.append(f"**Query**: {self._user_query}")

        if self._rewrite and self._rewrite != self._user_query:
            lines.append(f"**Rewrite**: {self._rewrite}")

        lines.append(f"**Router** → `{self._router_decision}`: {self._router_reason}")

        for tex in self._tool_executions:
            tool_label = tex["tool"]
            if tex["code"]:
                lines.append(f"**{tool_label} Code**: `{tex['code'][:200]}`")
            if tex["result"]:
                lines.append(f"**{tool_label} Result**: {tex['result'][:300]}")
            if tex["error"]:
                lines.append(f"**{tool_label} Error**: {tex['error']}")

        return "\n".join(lines)
