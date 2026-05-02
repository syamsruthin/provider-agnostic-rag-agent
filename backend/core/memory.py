"""
Memory — DEPRECATED
=====================
This module has been replaced by LangGraph's built-in SqliteSaver checkpointer.

Conversation persistence is now handled automatically by the LangGraph
StateGraph in `backend/agents/orchestrator.py`. Each session maps to a
LangGraph `thread_id`, and the checkpointer stores state in
`backend/data/checkpoints.db`.

This file is kept as a placeholder for backwards compatibility.
See: backend/agents/orchestrator.py for the new implementation.
"""

# No-op: All memory management is now in LangGraph's SqliteSaver checkpointer.
# See backend/agents/orchestrator.py :: graph.compile(checkpointer=_checkpointer)
