"""
LLM-as-Judge — semantic constraint evaluation for agent responses.

Keyword/regex constraints can only catch literal matches. An LLM judge
evaluates the *meaning* of a response against a business rule, catching
paraphrases, hints, and indirect violations that patterns miss.

Usage::

    from agentconfig.semantic.judge import LLMJudge, semantic_judge_constraint

    judge = LLMJudge(llm_fn=my_llm)  # any (prompt) -> str callable

    constraint = semantic_judge_constraint(
        id="no-pricing-semantic",
        description="Never reveal pricing information, even indirectly or through hints",
        judge_fn=judge.judge,
        action="block",
    )

    engine.add(constraint)
    result = engine.check("Our premium tier starts at around ninety-nine dollars a month")
    # → blocked, even though no keyword list contained "$99"

The judge prompt asks the model to answer with ``PASS`` or ``FAIL`` followed
by a one-line reason; parsing is tolerant of formatting noise. If the judge
cannot produce a parseable verdict, the response is treated as passed
(fail-open) — a judge outage should not take down the agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from agentconfig.semantic.constraint import (
    Constraint,
    ConstraintAction,
    ConstraintType,
)


# ── Verdict ──────────────────────────────────────────────────────────────

@dataclass
class JudgeVerdict:
    """Outcome of one semantic-judge evaluation."""
    passed: bool
    reasoning: str = ""
    confidence: float = 1.0

    def __str__(self) -> str:  # pragma: no cover - convenience only
        icon = "PASS" if self.passed else "FAIL"
        return f"[{icon}] {self.reasoning}"


JudgeFunction = Callable[[str, str], JudgeVerdict]
"""Signature: (response_text, rule_description) -> JudgeVerdict."""


# ── LLM-backed judge ─────────────────────────────────────────────────────

class LLMJudge:
    """
    Wraps an LLM callable into a judge function.

    Args:
        llm_fn: Callable ``(prompt: str) -> str``. Works with any provider
                (OpenAI, Anthropic, Ollama, ...) — see AgentExecutor's
                ``llm_fn`` for the same pattern.
        model_hint: Optional model name embedded in the prompt for logging.

    Example::

        import openai
        client = openai.OpenAI()

        def my_llm(prompt: str) -> str:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content

        judge = LLMJudge(llm_fn=my_llm)
    """

    def __init__(self, llm_fn: Callable[[str], str], model_hint: str = "") -> None:
        self._llm_fn = llm_fn
        self._model_hint = model_hint

    def judge(self, response: str, rule: str) -> JudgeVerdict:
        """Evaluate ``response`` against ``rule``. Fail-open on errors."""
        prompt = self._build_prompt(response, rule)
        try:
            raw = self._llm_fn(prompt) or ""
        except Exception as e:  # noqa: BLE001 - fail-open on judge outage
            return JudgeVerdict(passed=True, reasoning=f"judge error (fail-open): {e}", confidence=0.0)
        return self._parse(raw)

    def _build_prompt(self, response: str, rule: str) -> str:
        return f"""You are a strict policy compliance judge for an AI agent.

Business rule:
"{rule}"

Agent response:
\"\"\"{response}\"\"\"

Does the response violate the rule? Judge the meaning, not just keywords:
paraphrases, hints, indirect reveals, and partial disclosures all count as
violations.

Answer on the FIRST line with exactly one word: PASS or FAIL.
On the second line, give a one-sentence reason."""  # noqa: E501

    def _parse(self, raw: str) -> JudgeVerdict:
        text = raw.strip()
        # Strip markdown fences if the model wrapped its answer
        if text.startswith("```"):
            text = text.strip("`").lstrip(" \n")
        first_line = text.split("\n", 1)[0].strip().upper()
        reasoning = text.split("\n", 1)[1].strip() if "\n" in text else ""

        if "PASS" in first_line and "FAIL" not in first_line:
            return JudgeVerdict(passed=True, reasoning=reasoning or "response complies")
        if "FAIL" in first_line:
            return JudgeVerdict(passed=False, reasoning=reasoning or "response violates the rule")
        # Unparseable verdict → fail-open
        return JudgeVerdict(
            passed=True,
            reasoning=f"unparseable judge output (fail-open): {raw[:120]!r}",
            confidence=0.0,
        )


# ── Convenience builders ─────────────────────────────────────────────────

def semantic_judge_constraint(
    id: str,
    description: str,
    judge_fn: JudgeFunction,
    action: str = "block",
    fallback_message: str = "I'm sorry, I can't help with that. Please contact our team directly.",
) -> Constraint:
    """
    Build a semantic-judge constraint.

    Args:
        id: Unique constraint id.
        description: The business rule, in plain language — this is the
                     criterion the judge evaluates against.
        judge_fn: Judge function, e.g. ``LLMJudge(...).judge``.
        action: One of "block" | "warn" | "replace" | "escalate".
        fallback_message: Replacement shown when action is block/replace.

    Example::

        constraint = semantic_judge_constraint(
            id="no-pricing-semantic",
            description="Never reveal pricing, even indirectly",
            judge_fn=LLMJudge(my_llm).judge,
        )
    """
    return Constraint(
        id=id,
        type=ConstraintType.SEMANTIC_JUDGE,
        description=description,
        action=ConstraintAction(action),
        fallback_message=fallback_message,
        judge_fn=judge_fn,
    )
