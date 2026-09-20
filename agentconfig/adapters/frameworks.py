"""
Framework adapters — enforce AgentConfig constraints on any agent framework.

Each adapter wraps a framework's agent entry point so its responses pass
through the AgentConfig constraint engine before reaching the user. The
wrappers are dependency-free: they work with plain callables that follow each
framework's calling convention, so you can test without installing the
framework and plug in the real object in production.

Supported conventions
---------------------
- LangGraph:  node functions ``node(state: dict) -> dict`` where the state
              carries ``messages`` (a list of message dicts/tuples).
- AutoGen:    reply functions ``reply(messages, sender=None, **kw) -> str``.
- CrewAI:     objects exposing ``kickoff(...) -> str`` or ``execute(...) -> str``.

Usage::

    from agentconfig.adapters.frameworks import (
        wrap_langgraph_node, wrap_autogen_reply, wrap_crewai_agent,
    )

    # LangGraph node
    safe_node = wrap_langgraph_node(my_node, config)

    # AutoGen reply function
    safe_reply = wrap_autogen_reply(my_reply_fn, config)

    # CrewAI agent object (duck-typed)
    safe_agent = wrap_crewai_agent(my_agent, config)
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

from agentconfig.semantic.config_gen import AgentConfig
from agentconfig.semantic.constraint import CheckResult, ConstraintAction, ConstraintEngine


class ConstraintBlocked(Exception):
    """Raised by adapters when a response is blocked by policy and no fallback is embedded."""

    def __init__(self, message: str, result: CheckResult) -> None:
        super().__init__(message)
        self.result = result


def enforce_response(config: AgentConfig, response: str) -> Tuple[str, CheckResult]:
    """
    Run a response through the config's constraint engine.

    Returns:
        ``(possibly_replaced_text, check_result)`` — blocked responses are
        replaced by the constraint's fallback message; escalations raise
        :class:`ConstraintBlocked`.
    """
    engine: ConstraintEngine = config.get_constraint_engine()
    result = engine.check(response)

    if result.should_escalate:
        raise ConstraintBlocked(
            result.violations[0].message if result.violations else "escalation triggered",
            result,
        )

    if result.blocked:
        fallback = "I'm sorry, I can't provide that information. Please contact our team."
        for v in result.violations:
            if v.action == ConstraintAction.BLOCK:
                for c in config.constraints:
                    cid = c.get("id") if isinstance(c, dict) else getattr(c, "id", None)
                    if cid == v.constraint_id:
                        fb = c.get("fallback_message") if isinstance(c, dict) else getattr(c, "fallback_message", None)
                        if fb:
                            fallback = fb
                        break
                break
        return fallback, result

    return response, result


# ── LangGraph ────────────────────────────────────────────────────────────

def _extract_langgraph_text(state: Dict[str, Any]) -> str:
    messages = state.get("messages") or []
    last = messages[-1] if messages else None
    if last is None:
        return ""
    if isinstance(last, str):
        return last
    if isinstance(last, dict):
        return str(last.get("content", ""))
    if isinstance(last, (tuple, list)) and len(last) >= 2:
        return str(last[1])
    return str(last)


def _set_langgraph_text(state: Dict[str, Any], text: str) -> Dict[str, Any]:
    messages = state.get("messages") or []
    if messages and isinstance(messages[-1], dict):
        messages[-1]["content"] = text
    elif messages and isinstance(messages[-1], (tuple, list)) and len(messages[-1]) >= 2:
        messages[-1] = (messages[-1][0], text)
    else:
        state["messages"] = [*messages, {"role": "assistant", "content": text}]
    return state


def wrap_langgraph_node(node_fn: Callable[[Dict[str, Any]], Dict[str, Any]], config: AgentConfig) -> Callable:
    """
    Wrap a LangGraph node function with constraint enforcement.

    The wrapper reads the last message from the returned state, enforces the
    config's constraints, and writes the (possibly replaced) text back.
    """
    def wrapped(state: Dict[str, Any]) -> Dict[str, Any]:
        result = node_fn(state)
        if not isinstance(result, dict):
            return result
        text = _extract_langgraph_text(result)
        safe_text, _ = enforce_response(config, text)
        return _set_langgraph_text(dict(result), safe_text)
    return wrapped


# ── AutoGen ──────────────────────────────────────────────────────────────

def wrap_autogen_reply(reply_fn: Callable, config: AgentConfig) -> Callable:
    """
    Wrap an AutoGen-style reply function ``reply(messages, sender, **kw)``.

    The string reply is enforced against the config's constraints.
    """
    def wrapped(messages=None, sender=None, **kwargs):
        reply = reply_fn(messages, sender, **kwargs) if kwargs or sender is not None else reply_fn(messages, sender)
        if not isinstance(reply, str):
            return reply
        safe_text, _ = enforce_response(config, reply)
        return safe_text
    return wrapped


# ── CrewAI ───────────────────────────────────────────────────────────────

def wrap_crewai_agent(agent_obj: Any, config: AgentConfig) -> Any:
    """
    Wrap a duck-typed CrewAI agent object.

    Intercepts ``kickoff`` and ``execute`` methods (whichever exist) and
    enforces constraints on their string results. The agent object is patched
    in place and also returned for convenience.
    """
    for method_name in ("kickoff", "execute"):
        original = getattr(agent_obj, method_name, None)
        if original is None or not callable(original):
            continue

        def make_safe(orig: Callable) -> Callable:
            def safe(*args, **kwargs):
                output = orig(*args, **kwargs)
                if isinstance(output, str):
                    safe_text, _ = enforce_response(config, output)
                    return safe_text
                return output
            return safe

        setattr(agent_obj, method_name, make_safe(original))
    return agent_obj
