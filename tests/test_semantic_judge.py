"""
Tests for LLM-as-judge semantic constraints (v2.1.0).
"""


from agentconfig.runtime.executor import AgentExecutor
from agentconfig.semantic.config_gen import AgentConfig
from agentconfig.semantic.constraint import (
    Constraint,
    ConstraintAction,
    ConstraintEngine,
    ConstraintType,
)
from agentconfig.semantic.judge import (
    JudgeVerdict,
    LLMJudge,
    semantic_judge_constraint,
)

# ── JudgeVerdict ────────────────────────────────────────────────────────

class TestJudgeVerdict:
    def test_pass_verdict(self):
        v = JudgeVerdict(passed=True, reasoning="looks fine")
        assert v.passed and v.reasoning == "looks fine"

    def test_str(self):
        assert "PASS" in str(JudgeVerdict(passed=True))
        assert "FAIL" in str(JudgeVerdict(passed=False))


# ── LLMJudge parsing ────────────────────────────────────────────────────

class TestLLMJudgeParsing:
    def _judge(self, reply):
        return LLMJudge(llm_fn=lambda prompt: reply)

    def test_parses_pass(self):
        v = self._judge("PASS\nThe response contains no pricing information.").judge("resp", "no pricing")
        assert v.passed is True
        assert "no pricing" in v.reasoning

    def test_parses_fail(self):
        v = self._judge("FAIL\nThe response reveals the monthly price.").judge("resp", "no pricing")
        assert v.passed is False
        assert "monthly price" in v.reasoning

    def test_parses_fenced_output(self):
        v = self._judge("```\nFAIL\nDiscloses the discount rate.\n```").judge("resp", "no pricing")
        assert v.passed is False

    def test_fail_open_on_llm_error(self):
        def broken(prompt):
            raise RuntimeError("rate limited")
        v = LLMJudge(llm_fn=broken).judge("resp", "rule")
        assert v.passed is True
        assert v.confidence == 0.0
        assert "fail-open" in v.reasoning

    def test_fail_open_on_unparseable(self):
        v = self._judge("The response is mostly okay I guess?").judge("resp", "rule")
        assert v.passed is True
        assert v.confidence == 0.0

    def test_prompt_contains_rule_and_response(self):
        captured = {}
        def capture(prompt):
            captured["prompt"] = prompt
            return "PASS"
        LLMJudge(llm_fn=capture).judge("agent said something", "no pricing")
        assert "no pricing" in captured["prompt"]
        assert "agent said something" in captured["prompt"]


# ── Constraint integration ──────────────────────────────────────────────

class TestSemanticJudgeConstraint:
    def _engine(self, reply=None, verdict=None):
        if verdict is not None:
            def judge_fn(response, rule):
                return verdict
        else:
            judge_fn = LLMJudge(llm_fn=lambda p: reply).judge
        constraint = semantic_judge_constraint(
            id="no-pricing-semantic",
            description="Never reveal pricing, even indirectly",
            judge_fn=judge_fn,
        )
        engine = ConstraintEngine()
        engine.add(constraint)
        return engine

    def test_blocks_when_judge_fails(self):
        engine = self._engine(reply="FAIL\nReveals the subscription price.")
        result = engine.check("Our plan costs about ninety-nine dollars monthly")
        assert result.blocked is True
        assert "Semantic judge failed" in result.violations[0].message

    def test_passes_when_judge_passes(self):
        engine = self._engine(reply="PASS\nNo pricing mentioned.")
        result = engine.check("I can help you with account questions!")
        assert result.passed is True

    def test_warn_action_does_not_block(self):
        constraint = semantic_judge_constraint(
            id="warn-sem",
            description="rule",
            judge_fn=lambda r, d: JudgeVerdict(passed=False, reasoning="violation"),
            action="warn",
        )
        engine = ConstraintEngine()
        engine.add(constraint)
        result = engine.check("text")
        assert result.blocked is False
        assert result.violations[0].action == ConstraintAction.WARN

    def test_no_judge_fn_passes(self):
        constraint = Constraint(
            id="no-judge",
            type=ConstraintType.SEMANTIC_JUDGE,
            description="rule",
        )
        engine = ConstraintEngine()
        engine.add(constraint)
        assert engine.check("anything").passed is True

    def test_to_dict_omits_judge_fn(self):
        constraint = semantic_judge_constraint(
            id="x", description="rule", judge_fn=lambda r, d: JudgeVerdict(passed=True)
        )
        d = constraint.to_dict()
        assert "judge_fn" not in d
        assert d["type"] == "semantic_judge"


# ── Executor integration ────────────────────────────────────────────────

class TestExecutorWithJudge:
    def test_executor_blocks_via_semantic_judge(self):
        judge = LLMJudge(llm_fn=lambda p: "FAIL\nDiscloses internal pricing.")

        config = AgentConfig(name="SupportAgent")
        # Live Constraint object keeps judge_fn alive through the engine rebuild
        config.constraints = [semantic_judge_constraint(
            id="no-pricing",
            description="Never reveal pricing, even indirectly",
            judge_fn=judge.judge,
        )]

        executor = AgentExecutor()  # mock echo LLM
        response, record = executor.chat(config, "How much does it cost?")
        assert "can't" in response.lower() or "sorry" in response.lower()
        assert record.violation_count == 1

    def test_config_to_dict_serializes_live_constraints(self):
        config = AgentConfig(name="Agent")
        config.constraints = [semantic_judge_constraint(
            id="no-pricing",
            description="Never reveal pricing",
            judge_fn=lambda r, d: JudgeVerdict(passed=True),
        )]
        d = config.to_dict()
        assert d["constraints"][0]["type"] == "semantic_judge"
        assert "judge_fn" not in d["constraints"][0]


# ── Schema validation ───────────────────────────────────────────────────

class TestSchemaWithJudgeConstraint:
    def test_semantic_judge_constraint_passes_validation(self):
        from agentconfig.validation import validate_dict
        result = validate_dict({
            "name": "Agent",
            "constraints": [{
                "id": "sem-1",
                "type": "semantic_judge",
                "description": "Never reveal pricing",
                "action": "block",
            }],
        })
        assert result.valid, [str(e) for e in result.errors]
