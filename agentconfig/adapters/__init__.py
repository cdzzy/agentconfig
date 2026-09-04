"""
Framework adapters — constraint enforcement for popular agent frameworks.

See :mod:`agentconfig.adapters.frameworks` for LangGraph / AutoGen / CrewAI
wrappers that route framework responses through AgentConfig constraints.
"""

from agentconfig.adapters.frameworks import (
    ConstraintBlocked,
    enforce_response,
    wrap_autogen_reply,
    wrap_crewai_agent,
    wrap_langgraph_node,
)

__all__ = [
    "ConstraintBlocked",
    "enforce_response",
    "wrap_autogen_reply",
    "wrap_crewai_agent",
    "wrap_langgraph_node",
]
