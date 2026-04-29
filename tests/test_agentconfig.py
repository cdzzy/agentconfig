"""
Tests for AgentConfig framework.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agentconfig.semantic.intent import IntentParser, AgentDomain, AgentTone
from agentconfig.semantic.constraint import (
    Constraint, ConstraintType, ConstraintAction, ConstraintEngine,
)
from agentconfig.semantic.config_gen import ConfigGenerator, AgentConfig, ModelConfig
from agentconfig.runtime.executor import AgentExecutor, RunStatus
from agentconfig.runtime.monitor import AgentMonitor


# ── Intent Parser ────────────────────────────────────────────────────────
class TestIntentParser:

    def setup_method(self):
        self.parser = IntentParser()

    def test_basic_parse(self):
        intent = self.parser.parse("This agent helps customers with support.", name="Bot")
        assert intent.name == "Bot"
        assert intent.purpose != ""

    def test_domain_detection_customer_service(self):
        intent = self.parser.parse("Handle customer complaints and refunds.")
        assert intent.domain == AgentDomain.CUSTOMER_SERVICE

    def test_domain_detection_sales(self):
        intent = self.parser.parse("This agent assists the sales team with leads and revenue.")
        assert intent.domain == AgentDomain.SALES

    def test_domain_detection_hr(self):
        intent = self.parser.parse("Help employees with HR policies and onboarding.")
        assert intent.domain == AgentDomain.HR

    def test_tone_detection_formal(self):
        intent = self.parser.parse("Respond in a formal and professional manner.")
        assert AgentTone.FORMAL in intent.tone

    def test_tone_detection_empathetic(self):
        intent = self.parser.parse("Be empathetic and compassionate with users.")
        assert AgentTone.EMPATHETIC in intent.tone

    def test_forbidden_topic_extraction(self):
        intent = self.parser.parse(
            "This agent must never mention competitor products or internal pricing."
        )
        assert len(intent.topics_forbidden) >= 1

    def test_escalation_trigger_extraction(self):
        intent = self.parser.parse(
            "Escalate when the customer asks for a refund over $500."
        )
        assert len(intent.escalation_triggers) >= 1

    def test_confirmation_extraction(self):
        intent = self.parser.parse(
            "Always confirm before processing any refund request."
        )
        assert len(intent.require_confirmation) >= 1

    def test_to_system_prompt_non_empty(self):
        intent = self.parser.parse("Help customers with product questions.", name="FAQ Bot")
        prompt = intent.to_system_prompt()
        assert "FAQ Bot" in prompt
        assert len(prompt) > 20

    def test_to_dict_and_from_dict(self):
        intent = self.parser.parse("Sales agent for B2B leads.", name="Sales Bot")
        d = intent.to_dict()
        restored = type(intent).from_dict(d)
        assert restored.name == intent.name
        assert restored.domain == intent.domain


# ── Constraint Engine ─────────────────────────────────────────────────────
class TestConstraintEngine:

    def test_forbidden_keyword_blocked(self):
        c = Constraint(
            id="test-1", type=ConstraintType.FORBIDDEN_KEYWORD,
            description="No pricing", keywords=["price", "cost"],
            action=ConstraintAction.BLOCK,
        )
        v = c.check("Our price is $100.")
        assert v is not None
        assert v.action == ConstraintAction.BLOCK

    def test_forbidden_keyword_passes(self):
        c = Constraint(
            id="test-2", type=ConstraintType.FORBIDDEN_KEYWORD,
            description="No pricing", keywords=["price", "cost"],
            action=ConstraintAction.BLOCK,
        )
        v = c.check("Hello, how can I help you?")
        assert v is None

    def test_max_length_violation(self):
        c = Constraint(
            id="test-3", type=ConstraintType.MAX_LENGTH,
            description="Short replies only", max_chars=10,
            action=ConstraintAction.WARN,
        )
        v = c.check("This response is definitely longer than ten characters.")
        assert v is not None

    def test_max_length_passes(self):
        c = Constraint(
            id="test-4", type=ConstraintType.MAX_LENGTH,
            description="Short", max_chars=100,
            action=ConstraintAction.WARN,
        )
        v = c.check("OK")
        assert v is None

    def test_required_keyword_missing(self):
        c = Constraint(
            id="test-5", type=ConstraintType.REQUIRED_KEYWORD,
            description="Must include disclaimer",
            keywords=["not legal advice"],
            action=ConstraintAction.BLOCK,
        )
        v = c.check("This is general information.")
        assert v is not None

    def test_required_keyword_present(self):
        c = Constraint(
            id="test-6", type=ConstraintType.REQUIRED_KEYWORD,
            description="Must include disclaimer",
            keywords=["not legal advice"],
            action=ConstraintAction.BLOCK,
        )
        v = c.check("This is not legal advice. Please consult a lawyer.")
        assert v is None

    def test_custom_regex(self):
        c = Constraint(
            id="test-7", type=ConstraintType.CUSTOM,
            description="No phone numbers", pattern=r"\d{3}-\d{4}",
            action=ConstraintAction.BLOCK,
        )
        v = c.check("Call us at 555-1234.")
        assert v is not None

    def test_engine_multiple_constraints(self):
        engine = ConstraintEngine()
        engine.add(Constraint(
            id="kw-1", type=ConstraintType.FORBIDDEN_KEYWORD,
            description="No swearing", keywords=["damn"],
            action=ConstraintAction.BLOCK,
        ))
        engine.add(Constraint(
            id="len-1", type=ConstraintType.MAX_LENGTH,
            description="Short", max_chars=20,
            action=ConstraintAction.WARN,
        ))

        result = engine.check("This is a perfectly fine response.")
        assert not result.blocked
        assert len(result.violations) == 1  # max_length

    def test_engine_serialization(self):
        engine = ConstraintEngine()
        engine.add(Constraint(
            id="ser-1", type=ConstraintType.FORBIDDEN_KEYWORD,
            description="No secret words", keywords=["secret"],
            action=ConstraintAction.BLOCK,
        ))
        data = engine.to_list()
        restored = ConstraintEngine.from_list(data)
        result = restored.check("This is secret info.")
        assert result.blocked


# ── Config Generator ──────────────────────────────────────────────────────
class TestConfigGenerator:

    def setup_method(self):
        self.parser = IntentParser()
        self.gen    = ConfigGenerator()

    def test_generate_basic(self):
        intent = self.parser.parse("Answer customer questions.", name="FAQ")
        config = self.gen.generate(intent)
        assert config.name == "FAQ"
        assert config.system_prompt != ""
        assert isinstance(config.constraints, list)

    def test_generate_with_model(self):
        intent = self.parser.parse("Sales agent.", name="Sales")
        model  = ModelConfig(model="gpt-4o", temperature=0.2)
        config = self.gen.generate(intent, model=model)
        assert config.model.model == "gpt-4o"
        assert config.model.temperature == 0.2

    def test_config_serialization(self):
        intent = self.parser.parse("HR helper.", name="HR Bot")
        config = self.gen.generate(intent)
        d = config.to_dict()
        restored = AgentConfig.from_dict(d)
        assert restored.config_id == config.config_id
        assert restored.name == config.name

    def test_config_json_roundtrip(self):
        intent = self.parser.parse("Legal FAQ bot.", name="Legal")
        config = self.gen.generate(intent)
        j = config.to_json()
        restored = AgentConfig.from_json(j)
        assert restored.name == "Legal"

    def test_config_save_load(self, tmp_path):
        intent = self.parser.parse("IT support bot.", name="IT Helper")
        config = self.gen.generate(intent)
        path = str(tmp_path / "cfg.json")
        config.save(path)
        loaded = AgentConfig.load(path)
        assert loaded.config_id == config.config_id


# ── Executor ──────────────────────────────────────────────────────────────
class TestAgentExecutor:

    def setup_method(self):
        parser = IntentParser()
        gen    = ConfigGenerator()
        intent = parser.parse(
            "Customer support agent. Never mention pricing.", name="Support"
        )
        self.config   = gen.generate(intent)
        self.executor = AgentExecutor()

    def test_basic_chat(self):
        response, record = self.executor.chat(self.config, "Hello!")
        assert response != ""
        assert record.turn_count == 1

    def test_multi_turn(self):
        sid = "test-multi"
        self.executor.chat(self.config, "Hello!", session_id=sid)
        self.executor.chat(self.config, "How are you?", session_id=sid)
        _, record = self.executor.chat(self.config, "Bye!", session_id=sid)
        assert record.turn_count == 3

    def test_constraint_blocks_response(self):
        from agentconfig.semantic.constraint import Constraint, ConstraintType, ConstraintAction
        from agentconfig.semantic.config_gen import AgentConfig

        # Build a config with a constraint that blocks "BLOCK_THIS"
        config = AgentConfig(
            name="Test", system_prompt="You are a test agent.",
            constraints=[{
                "id": "block-test",
                "type": "forbidden_keyword",
                "description": "block test",
                "keywords": ["BLOCK_THIS"],
                "action": "block",
                "fallback_message": "Blocked by constraint.",
                "pattern": "", "max_chars": 0, "min_chars": 0,
            }],
        )

        def bad_llm(messages):
            return "Here is BLOCK_THIS content."

        executor = AgentExecutor(llm_fn=bad_llm)
        response, record = executor.chat(config, "test")
        assert "Blocked" in response or response != "Here is BLOCK_THIS content."

    def test_end_session(self):
        sid = "end-test"
        self.executor.chat(self.config, "Hi", session_id=sid)
        record = self.executor.end_session(sid)
        assert record is not None
        assert record.status == RunStatus.COMPLETED


# ── Monitor ───────────────────────────────────────────────────────────────
class TestAgentMonitor:

    def setup_method(self):
        self.monitor = AgentMonitor()

    def _make_run(self, name="Bot", status=RunStatus.COMPLETED):
        from agentconfig.runtime.executor import RunRecord
        r = RunRecord(config_id="cfg-1", agent_name=name, status=status)
        r.ended_at = r.started_at
        return r

    def test_record_and_recent(self):
        self.monitor.record(self._make_run())
        self.monitor.record(self._make_run())
        recent = self.monitor.recent(n=10)
        assert len(recent) == 2

    def test_stats_total(self):
        for _ in range(5):
            self.monitor.record(self._make_run())
        stats = self.monitor.stats()
        assert stats["total_runs"] == 5

    def test_stats_by_agent(self):
        self.monitor.record(self._make_run(name="AgentA"))
        self.monitor.record(self._make_run(name="AgentB"))
        self.monitor.record(self._make_run(name="AgentA"))
        stats = self.monitor.stats()
        assert stats["agents"]["AgentA"]["total"] == 2
        assert stats["agents"]["AgentB"]["total"] == 1

    def test_stats_filter_by_agent(self):
        self.monitor.record(self._make_run(name="AgentA"))
        self.monitor.record(self._make_run(name="AgentB"))
        stats = self.monitor.stats(agent_name="AgentA")
        assert stats["total_runs"] == 1

    def test_clear(self):
        self.monitor.record(self._make_run())
        self.monitor.clear()
        stats = self.monitor.stats()
        assert stats["total_runs"] == 0

    def test_empty_stats(self):
        stats = self.monitor.stats()
        assert stats["total_runs"] == 0
        assert stats["total_violations"] == 0


# ── Flask API ─────────────────────────────────────────────────────────────
class TestFlaskAPI:

    def setup_method(self):
        from agentconfig.ui.app import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_index_page(self):
        r = self.client.get("/")
        assert r.status_code == 200

    def test_configure_page(self):
        r = self.client.get("/configure")
        assert r.status_code == 200

    def test_configs_page(self):
        r = self.client.get("/configs")
        assert r.status_code == 200

    def test_chat_page(self):
        r = self.client.get("/chat")
        assert r.status_code == 200

    def test_api_parse_intent(self):
        r = self.client.post("/api/parse-intent",
            json={"description": "Handle customer complaints politely.", "name": "Bot"},
            content_type="application/json")
        assert r.status_code == 200
        data = r.get_json()
        assert "intent" in data
        assert "system_prompt" in data

    def test_api_parse_intent_missing_desc(self):
        r = self.client.post("/api/parse-intent",
            json={"name": "Bot"},
            content_type="application/json")
        assert r.status_code == 400

    def test_api_generate_config(self):
        r = self.client.post("/api/generate-config",
            json={"description": "Sales agent for B2B.", "name": "Sales Bot"},
            content_type="application/json")
        assert r.status_code == 200
        data = r.get_json()
        assert "config" in data
        assert data["config"]["name"] == "Sales Bot"

    def test_api_stats(self):
        r = self.client.get("/api/stats")
        assert r.status_code == 200
        data = r.get_json()
        assert "total_runs" in data

    def test_api_runs(self):
        r = self.client.get("/api/runs")
        assert r.status_code == 200
        data = r.get_json()
        assert "runs" in data

    def test_api_chat_no_config(self):
        r = self.client.post("/api/chat",
            json={"message": "Hello!"},
            content_type="application/json")
        assert r.status_code == 200
        data = r.get_json()
        assert "response" in data

    def test_api_list_configs(self):
        r = self.client.get("/api/configs")
        assert r.status_code == 200
        data = r.get_json()
        assert "configs" in data

    def test_api_config_not_found(self):
        r = self.client.get("/api/configs/nonexistent-id-xyz")
        assert r.status_code == 404


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
