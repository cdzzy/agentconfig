"""Tests for the DSPy exporter (generated source and runtime behaviour)."""

import sys
import types
from pathlib import Path

import pytest

from agentconfig import (
    AgentConfig,
    AgentIntent,
    Constraint,
    ConstraintType,
    export_dspy_program,
    save_dspy_program,
)
from agentconfig.semantic.constraint import ConstraintAction


def _make_config(**overrides) -> AgentConfig:
    config = AgentConfig(
        config_id="cfg12345",
        name="Support Bot",
        version="1.2.3",
        system_prompt="You are Support Bot. Be polite, concise, and helpful.",
    )
    config.constraints = [
        Constraint(
            id="no-pricing",
            type=ConstraintType.FORBIDDEN_KEYWORD,
            description="Never reveal pricing or costs",
            keywords=["price", "$", "cost"],
            action=ConstraintAction.BLOCK,
        ),
        Constraint(
            id="short-replies",
            type=ConstraintType.MAX_LENGTH,
            description="Keep replies under 80 characters",
            max_chars=80,
        ),
    ]
    config.tools_enabled = ["search_kb", "send_reply"]
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def _exec_generated(source: str):
    """Execute generated source against a minimal fake ``dspy`` module."""
    fake = types.ModuleType("dspy")
    configured: list[dict] = []

    class Prediction(dict):
        def __getattr__(self, item):
            try:
                return self[item]
            except KeyError as exc:  # pragma: no cover - defensive
                raise AttributeError(item) from exc

    class Signature:
        pass

    class Module:
        def __init__(self):
            pass

    class InputField:
        def __init__(self, desc=""):
            self.desc = desc

    class OutputField(InputField):
        pass

    class LM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Predictor:
        def __init__(self, signature):
            self.signature = signature

        def __call__(self, **kwargs):
            return Prediction(
                answer="Our price is $99 per seat.",
                reasoning="The user asked about plans.",
            )

    def configure(**kwargs):
        configured.append(kwargs)

    fake.Signature = Signature
    fake.Module = Module
    fake.InputField = InputField
    fake.OutputField = OutputField
    fake.ChainOfThought = Predictor
    fake.Predict = Predictor
    fake.Prediction = Prediction
    fake.LM = LM
    fake.configure = configure

    namespace = {"__name__": "generated_dspy_program"}
    previous = sys.modules.get("dspy")
    sys.modules["dspy"] = fake
    try:
        exec(compile(source, "<dspy-export>", "exec"), namespace)
    finally:
        if previous is None:
            sys.modules.pop("dspy", None)
        else:
            sys.modules["dspy"] = previous
    return namespace, configured


class TestExportSource:
    def test_generated_source_compiles(self):
        source = export_dspy_program(_make_config())
        compile(source, "<dspy-export>", "exec")

    def test_class_names_follow_config_name(self):
        source = export_dspy_program(_make_config())
        assert "class SupportBotSignature(dspy.Signature):" in source
        assert "class SupportBotProgram(dspy.Module):" in source

    def test_module_name_overrides_class_names(self):
        source = export_dspy_program(_make_config(), module_name="CustomerSupport")
        assert "class CustomerSupportSignature(dspy.Signature):" in source
        assert "class CustomerSupportProgram(dspy.Module):" in source

    def test_sanitises_unsafe_module_names(self):
        source = export_dspy_program(_make_config(), module_name="support bot!")
        assert "class SupportBotSignature(dspy.Signature):" in source

    def test_non_ascii_name_falls_back_to_config_id(self):
        config = _make_config(name="客服助手", config_id="abc12345")
        source = export_dspy_program(config)
        assert "class Agentabc12345Signature(dspy.Signature):" in source

    def test_instructions_carry_system_prompt_and_constraints(self):
        source = export_dspy_program(_make_config())
        assert "You are Support Bot. Be polite, concise, and helpful." in source
        assert "Hard constraints (never violate):" in source
        assert "Never reveal pricing or costs" in source
        assert "Keep replies under 80 characters" in source

    def test_uses_intent_prompt_when_system_prompt_is_empty(self):
        intent = AgentIntent(
            name="Policy Bot",
            purpose="Answer policy questions.",
            actions_forbidden=["revealing confidential data"],
        )
        config = _make_config(name="Policy Bot", system_prompt="", intent=intent)
        source = export_dspy_program(config)
        assert "Answer policy questions." in source
        assert "You must NEVER: revealing confidential data." in source

    def test_reasoning_toggle(self):
        with_reasoning = export_dspy_program(_make_config())
        without_reasoning = export_dspy_program(_make_config(), reasoning=False)
        assert "self.generate = dspy.ChainOfThought(SupportBotSignature)" in with_reasoning
        assert "self.generate = dspy.Predict(SupportBotSignature)" in without_reasoning
        assert "ChainOfThought" not in without_reasoning

    def test_optimizer_template_is_optional(self):
        with_optimizer = export_dspy_program(_make_config())
        without_optimizer = export_dspy_program(_make_config(), include_optimizer=False)
        assert "BootstrapFewShotWithRandomSearch" in with_optimizer
        assert "GEPA" in with_optimizer
        assert "SIMBA" in with_optimizer
        assert "GEPA" not in without_optimizer

    def test_tools_are_listed_as_comments(self):
        source = export_dspy_program(_make_config())
        assert "# - search_kb" in source
        assert "# - send_reply" in source


class TestModelMapping:
    def test_openai_model_string(self):
        config = _make_config()
        config.model.model = "gpt-4o-mini"
        source = export_dspy_program(config)
        assert "'model': 'openai/gpt-4o-mini'" in source

    def test_anthropic_model_string(self):
        config = _make_config()
        config.model.provider = "anthropic"
        config.model.model = "claude-3-5-sonnet"
        source = export_dspy_program(config)
        assert "'model': 'anthropic/claude-3-5-sonnet'" in source

    def test_ollama_model_string_and_api_base(self):
        config = _make_config()
        config.model.provider = "ollama"
        config.model.model = "llama3"
        config.model.api_base = "http://localhost:11434"
        source = export_dspy_program(config)
        assert "'model': 'ollama_chat/llama3'" in source
        assert "'api_base': 'http://localhost:11434'" in source

    def test_unknown_provider_keeps_model_name(self):
        config = _make_config()
        config.model.provider = "acme"
        config.model.model = "acme-llm"
        source = export_dspy_program(config)
        assert "'model': 'acme-llm'" in source

    def test_prefixed_model_is_not_prefixed_twice(self):
        config = _make_config()
        config.model.model = "openai/gpt-4o"
        source = export_dspy_program(config)
        assert "'model': 'openai/gpt-4o'" in source


class TestMetadata:
    def test_metadata_and_lm_args_are_embedded(self):
        source = export_dspy_program(_make_config())
        assert "'config_id': 'cfg12345'" in source
        assert "'version': '1.2.3'" in source
        assert "'temperature': 0.7" in source
        assert "'max_tokens': 1024" in source
        assert "'tools_enabled': ['search_kb', 'send_reply']" in source

    def test_no_constraints_yields_empty_list(self):
        config = _make_config(constraints=[])
        source = export_dspy_program(config)
        assert "CONSTRAINTS: list[dict[str, Any]] = []" in source


class TestGeneratedRuntime:
    def test_program_runs_and_attaches_violations(self):
        config = _make_config()
        namespace, configured = _exec_generated(export_dspy_program(config))

        program = namespace["build_program"]()
        prediction = program.forward("How much does it cost?")

        assert prediction["answer"] == "Our price is $99 per seat."
        assert any("no-pricing" in item for item in prediction["violations"])
        assert configured, "build_program() should configure a default LM"
        assert configured[0]["lm"].kwargs["model"] == "openai/gpt-4o-mini"

    def test_check_constraints_mirrors_engine_rules(self):
        config = _make_config(
            constraints=[
                Constraint(
                    id="secret-pattern",
                    type=ConstraintType.CUSTOM,
                    description="Block the word secret",
                    pattern=r"\bsecret\b",
                ),
                Constraint(
                    id="refund-escalation",
                    type=ConstraintType.ESCALATION,
                    description="Escalate refund requests",
                    keywords=["refund"],
                ),
                Constraint(
                    id="tone",
                    type=ConstraintType.TONE_CHECK,
                    description="Apologise when needed",
                    keywords=["sorry", "apologise"],
                ),
                Constraint(
                    id="min-length",
                    type=ConstraintType.MIN_LENGTH,
                    description="Minimum length",
                    min_chars=10,
                ),
            ]
        )
        namespace, _ = _exec_generated(export_dspy_program(config))
        check = namespace["check_constraints"]

        assert any("secret-pattern" in item for item in check("the secret plan"))
        assert any("refund-escalation" in item for item in check("I want a refund"))
        assert any("tone" in item for item in check("ok"))
        assert any("min-length" in item for item in check("short"))
        assert check("Sorry, I can help with that request.") == []

    def test_unknown_constraint_types_are_ignored(self):
        config = _make_config(
            constraints=[
                Constraint(
                    id="semantic",
                    type=ConstraintType.SEMANTIC_JUDGE,
                    description="Judge the answer semantically",
                )
            ]
        )
        namespace, _ = _exec_generated(export_dspy_program(config))
        assert namespace["check_constraints"]("anything") == []

    def test_predict_mode_runs(self):
        config = _make_config()
        namespace, _ = _exec_generated(
            export_dspy_program(config, reasoning=False)
        )
        program = namespace["build_program"]()
        assert program.forward("hi")["answer"]


class TestSave:
    def test_save_writes_file_and_creates_parents(self, tmp_path: Path):
        target = tmp_path / "generated" / "support_bot.py"
        path = save_dspy_program(_make_config(), str(target))

        assert path == str(target)
        assert target.exists()
        assert target.read_text(encoding="utf-8") == export_dspy_program(_make_config())

    def test_type_error_for_non_config(self):
        with pytest.raises(TypeError):
            export_dspy_program("not a config")  # type: ignore[arg-type]
