"""
Tests for framework adapters (v2.2.0).

Uses duck-typed callables that follow each framework's calling convention —
no framework packages required.
"""

import pytest

from agentconfig.semantic.config_gen import AgentConfig
from agentconfig.adapters.frameworks import (
    ConstraintBlocked,
    enforce_response,
    wrap_autogen_reply,
    wrap_crewai_agent,
    wrap_langgraph_node,
)


def make_config():
    config = AgentConfig(name="GuardedAgent")
    config.constraints = [{
        "id": "no-pricing",
        "type": "forbidden_keyword",
        "description": "Never reveal pricing",
        "action": "block",
        "keywords": ["price", "$", "cost"],
        "fallback_message": "Pricing is handled by our sales team.",
    }]
    return config


class TestEnforceResponse:
    def test_clean_response_passes_through(self):
        config = make_config()
        text, result = enforce_response(config, "Here is what you asked for!")
        assert text == "Here is what you asked for!"
        assert not result.blocked

    def test_blocked_response_replaced_with_fallback(self):
        config = make_config()
        text, result = enforce_response(config, "The price is $99")
        assert text == "Pricing is handled by our sales team."
        assert result.blocked

    def test_escalation_raises(self):
        config = make_config()
        config.constraints = [{
            "id": "escalate-angry",
            "type": "escalation",
            "description": "Escalate when angry",
            "keywords": ["manager"],
        }]
        with pytest.raises(ConstraintBlocked):
            enforce_response(config, "I want to talk to the manager")


class TestLangGraphAdapter:
    def test_blocks_forbidden_content_in_node_output(self):
        config = make_config()

        def my_node(state):
            return {"messages": state["messages"] + [{"role": "assistant", "content": "The cost is $50"}]}

        safe_node = wrap_langgraph_node(my_node, config)
        out = safe_node({"messages": [{"role": "user", "content": "hi"}]})
        last = out["messages"][-1]
        assert last["content"] == "Pricing is handled by our sales team."

    def test_passes_clean_content(self):
        config = make_config()

        def my_node(state):
            return {"messages": [{"role": "assistant", "content": "All good!"}]}

        safe_node = wrap_langgraph_node(my_node, config)
        out = safe_node({"messages": []})
        assert out["messages"][-1]["content"] == "All good!"

    def test_handles_tuple_messages(self):
        config = make_config()

        def my_node(state):
            return {"messages": [("assistant", "total cost $5")]}

        safe_node = wrap_langgraph_node(my_node, config)
        out = safe_node({"messages": []})
        assert out["messages"][-1][1] == "Pricing is handled by our sales team."


class TestAutoGenAdapter:
    def test_blocks_forbidden_reply(self):
        config = make_config()

        def my_reply(messages, sender=None):
            return "that will cost you $20"

        safe_reply = wrap_autogen_reply(my_reply, config)
        assert safe_reply([{"content": "hi"}]) == "Pricing is handled by our sales team."

    def test_passes_clean_reply(self):
        config = make_config()

        def my_reply(messages, sender=None):
            return "happy to help"

        safe_reply = wrap_autogen_reply(my_reply, config)
        assert safe_reply([{"content": "hi"}]) == "happy to help"


class TestCrewAIAdapter:
    def test_kickoff_is_wrapped(self):
        config = make_config()

        class FakeCrew:
            def kickoff(self, **kwargs):
                return "the price is $10"

        safe_agent = wrap_crewai_agent(FakeCrew(), config)
        assert safe_agent.kickoff() == "Pricing is handled by our sales team."

    def test_execute_is_wrapped(self):
        config = make_config()

        class FakeAgent:
            def execute(self, task):
                return "no pricing here"

        safe_agent = wrap_crewai_agent(FakeAgent(), config)
        assert safe_agent.execute("task") == "no pricing here"

    def test_non_string_output_passthrough(self):
        config = make_config()

        class FakeAgent:
            def kickoff(self):
                return {"output": {"price": 10}}

        safe_agent = wrap_crewai_agent(FakeAgent(), config)
        assert safe_agent.kickoff() == {"output": {"price": 10}}
