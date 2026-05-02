"""
Trace Logger — Per-Node Step Tracing
======================================
Every graph node logs its own step as it executes. Each step captures:
  - Step number & node name
  - Timestamp (UTC)
  - Input / Output / Reasoning
  - Duration
  - Any metadata (retry count, error context, etc.)

Produces:
  1. JSONL machine log ({session_id}.jsonl)
  2. Markdown human-readable report (trace_{trace_id}.md)
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from backend.core.config import LOGS_DIR


class TraceLogger:
    """
    Per-trace logger that accumulates per-node steps and writes
    both JSONL (machine) and Markdown (human) logs.

    Usage (called from each graph node):
        logger = TraceLogger(trace_id="abc-123", session_id="sess-456")

        logger.step("rewrite",
            input="Find me a heart doctor in Texas",
            output="Find me a Cardiologist in TX",
            reasoning="LLM normalized: heart doctor → Cardiologist, Texas → TX")

        logger.step("route",
            input="Find me a Cardiologist in TX",
            output="CSV_TOOL",
            reasoning="Doctor search by specialty and location",
            metadata={"tools_list": ["CSV_TOOL"]})

        logger.flush()
    """

    def __init__(self, trace_id: str, session_id: str):
        self.trace_id = trace_id
        self.session_id = session_id
        self._steps: list[dict] = []
        self._step_counter = 0
        self._start_time = time.monotonic()

        # Ensure logs dir exists
        LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------
    # Core: log a single step
    # -----------------------------------------------------------------
    def step(
        self,
        node: str,
        *,
        input: str = "",
        output: str = "",
        reasoning: str = "",
        duration_ms: float = 0,
        metadata: dict | None = None,
    ) -> None:
        """
        Log a single graph node execution step.

        Args:
            node: Name of the graph node (e.g., "rewrite", "route", "execute_sql")
            input: What the node received as input
            output: What the node produced
            reasoning: Why the node made the decisions it did
            duration_ms: How long the step took (in milliseconds)
            metadata: Any additional key-value data (retry count, error, tools_list, etc.)
        """
        self._step_counter += 1
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "step": self._step_counter,
            "node": node,
            "input": input,
            "output": output,
            "reasoning": reasoning,
            "duration_ms": round(duration_ms, 1),
            "metadata": metadata or {},
        }
        self._steps.append(entry)

    # -----------------------------------------------------------------
    # Flush to disk
    # -----------------------------------------------------------------
    def flush(self) -> tuple[Path, Path]:
        """Write JSONL and Markdown files. Returns (jsonl_path, md_path)."""
        jsonl_path = self._write_jsonl()
        md_path = self._write_markdown()
        return jsonl_path, md_path

    def _write_jsonl(self) -> Path:
        """Append all step entries to the session JSONL file."""
        jsonl_path = LOGS_DIR / f"{self.session_id}.jsonl"
        with open(jsonl_path, "a") as f:
            for entry in self._steps:
                f.write(json.dumps(entry, default=str) + "\n")
        return jsonl_path

    def _write_markdown(self) -> Path:
        """Write the full human-readable Markdown trace report."""
        total_duration = (time.monotonic() - self._start_time) * 1000  # ms
        md_path = LOGS_DIR / f"trace_{self.trace_id[:8]}.md"

        lines = [
            f"# Trace Report: `{self.trace_id[:8]}`",
            f"**Session**: `{self.session_id[:8]}...`  |  "
            f"**Timestamp**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  |  "
            f"**Total Steps**: {self._step_counter}  |  "
            f"**Total Duration**: {total_duration:.0f}ms",
            "",
            "---",
            "",
        ]

        for s in self._steps:
            step_num = s["step"]
            node = s["node"]
            duration = s["duration_ms"]
            meta = s.get("metadata", {})

            # Header with timing
            header = f"## Step {step_num}: {node}"
            if meta.get("attempt"):
                header += f" — Attempt {meta['attempt']}"
            if meta.get("react_iteration"):
                header += f" (ReAct iteration {meta['react_iteration']})"
            if duration > 0:
                header += f"  `({duration:.0f}ms)`"
            lines.append(header)

            # Input
            if s["input"]:
                input_text = s["input"]
                if len(input_text) > 500:
                    input_text = input_text[:500] + "..."
                lines.append(f"- **Input**: {input_text}")

            # Output
            if s["output"]:
                output_text = s["output"]
                if "\n" in output_text or len(output_text) > 200:
                    # Multi-line output in code block
                    preview = output_text[:1500]
                    lines.append(f"- **Output**:")
                    lines.append(f"```\n{preview}\n```")
                else:
                    lines.append(f"- **Output**: {output_text}")

            # Reasoning / Decision
            if s["reasoning"]:
                lines.append(f"- **Reasoning**: {s['reasoning']}")

            # Metadata (key-value pairs)
            for key, val in meta.items():
                if key in ("attempt", "react_iteration"):
                    continue  # already in header
                if isinstance(val, str) and len(val) > 300:
                    lines.append(f"- **{_format_key(key)}**:")
                    lines.append(f"```\n{val[:1000]}\n```")
                elif isinstance(val, list):
                    lines.append(f"- **{_format_key(key)}**: {', '.join(str(v) for v in val)}")
                elif val is not None and val != "":
                    lines.append(f"- **{_format_key(key)}**: {val}")

            lines.append("")

        md_content = "\n".join(lines)
        md_path.write_text(md_content)
        return md_path

    # -----------------------------------------------------------------
    # In-memory Markdown (for API response / UI sidebar)
    # -----------------------------------------------------------------
    def get_markdown_report(self) -> str:
        """Return a compact Markdown report for the API response (UI sidebar)."""
        total_duration = (time.monotonic() - self._start_time) * 1000
        lines = [
            f"**Trace**: `{self.trace_id[:8]}` | "
            f"**Steps**: {self._step_counter} | "
            f"**Duration**: {total_duration:.0f}ms",
            "",
        ]

        for s in self._steps:
            node = s["node"]
            meta = s.get("metadata", {})
            duration = s["duration_ms"]

            # Compact one-liner per step
            prefix = f"**{s['step']}. {node}**"
            if duration > 0:
                prefix += f" `({duration:.0f}ms)`"

            if node == "rewrite":
                if s["input"] != s["output"] and s["output"]:
                    lines.append(f"{prefix}: `{s['input']}` → `{s['output']}`")
                else:
                    lines.append(f"{prefix}: *(no change)*")

            elif node == "route":
                lines.append(f"{prefix}: → `{s['output']}` — {s['reasoning']}")
                if meta.get("tools_list"):
                    lines.append(f"   Tools: {meta['tools_list']}")

            elif node.startswith("execute"):
                tool = meta.get("tool", node)
                if meta.get("error"):
                    lines.append(f"{prefix}: ⚠️ `{tool}` error: {meta['error']}")
                else:
                    code = meta.get("code", "")
                    if code:
                        lines.append(f"{prefix}: `{tool}` → `{code[:150]}`")
                    else:
                        lines.append(f"{prefix}: `{tool}` → {s['output'][:200]}")

            elif node == "check_retry":
                lines.append(f"{prefix}: {s['reasoning']}")

            elif node == "synthesize":
                answer_preview = s["output"][:200] + "..." if len(s["output"]) > 200 else s["output"]
                lines.append(f"{prefix}: {answer_preview}")

            elif node == "validate":
                verdict = meta.get("verdict", s["output"])
                lines.append(f"{prefix}: **{verdict}** — {s['reasoning']}")

            elif node == "react_reroute":
                lines.append(f"{prefix}: Looping back to route (iteration {meta.get('react_count', '?')})")

            elif node == "finalize":
                lines.append(f"{prefix}: ✅ Done")

            else:
                lines.append(f"{prefix}: {s['output'][:200]}")

        return "\n".join(lines)


def _format_key(key: str) -> str:
    """Convert snake_case to Title Case for display."""
    return key.replace("_", " ").title()
