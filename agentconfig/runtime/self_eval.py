"""
AgentSelfEval — self-evaluation and adaptive prompt refinement.

Inspired by hermes-agent's self-improvement loop, this module enables
agents to evaluate their own responses and iteratively refine system
prompts based on evaluation feedback.

Features:
- Configurable evaluation criteria (relevance, accuracy, helpfulness)
- Self-evaluation via LLM judge or rule-based checks
- Prompt refinement suggestions based on failure patterns
- Evaluation history with trend analysis
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


class EvalOutcome(str, Enum):
    """Result of a self-evaluation check."""
    PASS = "pass"
    FAIL = "fail"
    PARTIAL = "partial"
    SKIP = "skip"


class EvalCriterion(str, Enum):
    """Built-in evaluation criteria."""
    RELEVANCE = "relevance"
    ACCURACY = "accuracy"
    COMPLETENESS = "completeness"
    TONE = "tone"
    CONSTRAINT_COMPLIANCE = "constraint_compliance"
    CUSTOM = "custom"


@dataclass
class EvalCheck:
    """A single evaluation check definition."""
    id: str
    criterion: EvalCriterion
    description: str
    weight: float = 1.0
    check_fn: Optional[Callable[[str, str, Dict], EvalOutcome]] = None
    llm_prompt_template: Optional[str] = None


@dataclass
class EvalResult:
    """Result of evaluating a single check."""
    check_id: str
    criterion: EvalCriterion
    outcome: EvalOutcome
    score: float  # 0.0 to 1.0
    feedback: str = ""
    suggestion: str = ""


@dataclass
class EvalReport:
    """Complete evaluation report for a single response."""
    report_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    user_message: str = ""
    agent_response: str = ""
    results: List[EvalResult] = field(default_factory=list)
    overall_score: float = 0.0
    passed: bool = False
    refinement_hints: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "timestamp": self.timestamp,
            "user_message": self.user_message,
            "agent_response": self.agent_response[:500],
            "overall_score": round(self.overall_score, 3),
            "passed": self.passed,
            "results": [
                {
                    "check_id": r.check_id,
                    "criterion": r.criterion.value,
                    "outcome": r.outcome.value,
                    "score": round(r.score, 3),
                    "feedback": r.feedback,
                    "suggestion": r.suggestion,
                }
                for r in self.results
            ],
            "refinement_hints": self.refinement_hints,
        }


class AgentSelfEval:
    """
    Self-evaluation engine for agent responses.

    Evaluates agent outputs against configurable criteria and produces
    actionable refinement hints for prompt improvement.

    Usage::

        evaluator = AgentSelfEval()

        # Add built-in checks
        evaluator.add_check(EvalCheck(
            id="no_hallucination",
            criterion=EvalCriterion.ACCURACY,
            description="Response should not contain unverifiable claims",
            check_fn=my_accuracy_check,
        ))

        # Or use LLM-based evaluation
        evaluator.add_check(EvalCheck(
            id="relevance_check",
            criterion=EvalCriterion.RELEVANCE,
            description="Response should directly address the user question",
            llm_prompt_template="Rate the relevance...",
        ))

        # Evaluate
        report = evaluator.evaluate(
            user_message="What is the capital of France?",
            agent_response="The capital of France is Paris.",
            llm_fn=my_llm,
        )

        if report.passed:
            print("Response passed all checks")
        else:
            for hint in report.refinement_hints:
                print(f"Hint: {hint}")
    """

    def __init__(
        self,
        pass_threshold: float = 0.7,
        max_checks: int = 20,
    ):
        self._checks: List[EvalCheck] = []
        self._history: List[EvalReport] = []
        self.pass_threshold = pass_threshold
        self.max_checks = max_checks

    def add_check(self, check: EvalCheck) -> None:
        """Register an evaluation check."""
        if len(self._checks) >= self.max_checks:
            raise ValueError(f"Maximum of {self.max_checks} checks reached")
        self._checks.append(check)

    def remove_check(self, check_id: str) -> None:
        """Remove a check by ID."""
        self._checks = [c for c in self._checks if c.id != check_id]

    def evaluate(
        self,
        user_message: str,
        agent_response: str,
        context: Optional[Dict[str, Any]] = None,
        llm_fn: Optional[Callable] = None,
    ) -> EvalReport:
        """
        Run all registered checks against a response.

        Args:
            user_message: The original user input
            agent_response: The agent's response to evaluate
            context: Optional additional context (config, metadata, etc.)
            llm_fn: LLM function for LLM-based checks. Takes a string prompt
                    and returns a string response.

        Returns:
            EvalReport with detailed results and refinement hints.
        """
        ctx = context or {}
        results: List[EvalResult] = []

        total_weight = sum(c.weight for c in self._checks) or 1.0
        weighted_score = 0.0

        for check in self._checks:
            if check.check_fn is not None:
                # Rule-based evaluation
                outcome = check.check_fn(user_message, agent_response, ctx)
                score = {EvalOutcome.PASS: 1.0, EvalOutcome.PARTIAL: 0.5,
                         EvalOutcome.FAIL: 0.0, EvalOutcome.SKIP: 1.0}.get(outcome, 0.5)
                feedback = f"Rule-based: {outcome.value}"
                suggestion = ""
                if outcome == EvalOutcome.FAIL:
                    suggestion = self._generate_suggestion(check, user_message, agent_response)

            elif check.llm_prompt_template is not None and llm_fn is not None:
                # LLM-based evaluation
                score, feedback, suggestion = self._llm_evaluate(
                    check, user_message, agent_response, llm_fn
                )
                outcome = (
                    EvalOutcome.PASS if score >= 0.8
                    else EvalOutcome.PARTIAL if score >= 0.5
                    else EvalOutcome.FAIL
                )
            else:
                outcome = EvalOutcome.SKIP
                score = 1.0
                feedback = "Skipped: no check function or LLM available"
                suggestion = ""

            results.append(EvalResult(
                check_id=check.id,
                criterion=check.criterion,
                outcome=outcome,
                score=score,
                feedback=feedback,
                suggestion=suggestion,
            ))
            weighted_score += score * (check.weight / total_weight)

        report = EvalReport(
            user_message=user_message,
            agent_response=agent_response,
            results=results,
            overall_score=weighted_score,
            passed=weighted_score >= self.pass_threshold,
        )

        # Generate refinement hints from failures
        report.refinement_hints = self._collect_hints(results)

        self._history.append(report)
        return report

    def _llm_evaluate(
        self,
        check: EvalCheck,
        user_message: str,
        agent_response: str,
        llm_fn: Callable,
    ) -> Tuple[float, str, str]:
        """Evaluate using an LLM judge."""
        prompt = (
            f"{check.llm_prompt_template}\n\n"
            f"User message: {user_message}\n"
            f"Agent response: {agent_response}\n\n"
            f"Respond in JSON format with keys: score (0-1), feedback (string), suggestion (string)"
        )
        try:
            raw = llm_fn([{"role": "user", "content": prompt}])
            # Parse JSON from response
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1])
            parsed = json.loads(cleaned)
            score = float(parsed.get("score", 0.5))
            score = max(0.0, min(1.0, score))
            feedback = str(parsed.get("feedback", ""))
            suggestion = str(parsed.get("suggestion", ""))
            return score, feedback, suggestion
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            return 0.5, f"LLM evaluation failed: {e}", ""

    def _generate_suggestion(
        self,
        check: EvalCheck,
        user_message: str,
        agent_response: str,
    ) -> str:
        """Generate a suggestion for a failed rule-based check."""
        suggestions = {
            EvalCriterion.RELEVANCE: (
                "Consider adding instructions to focus the response on the user's "
                "specific question. Add: 'Always address the user's question directly "
                "before providing additional context.'"
            ),
            EvalCriterion.ACCURACY: (
                "Add a verification instruction: 'Verify all factual claims before "
                "including them in your response. If uncertain, explicitly state the "
                "limitation.'"
            ),
            EvalCriterion.COMPLETENESS: (
                "Add a completeness instruction: 'Ensure your response covers all "
                "aspects of the user's request. Use a checklist if the question has "
                "multiple parts.'"
            ),
            EvalCriterion.TONE: (
                "Consider refining the tone instruction in your system prompt to be "
                "more explicit about the desired communication style."
            ),
            EvalCriterion.CONSTRAINT_COMPLIANCE: (
                "Strengthen the constraint wording or add fallback instructions for "
                "edge cases where the agent might violate constraints."
            ),
            EvalCriterion.CUSTOM: (
                f"Review the '{check.description}' check and consider adjusting "
                f"the system prompt to address this criterion."
            ),
        }
        return suggestions.get(check.criterion, "Review and refine the system prompt.")

    def _collect_hints(self, results: List[EvalResult]) -> List[str]:
        """Collect actionable hints from failed checks."""
        hints = []
        for r in results:
            if r.outcome in (EvalOutcome.FAIL, EvalOutcome.PARTIAL):
                if r.suggestion:
                    hints.append(f"[{r.criterion.value}] {r.suggestion}")
        return hints

    def stats(self) -> Dict[str, Any]:
        """Get aggregate statistics from evaluation history."""
        if not self._history:
            return {"total_evals": 0}

        total = len(self._history)
        passed = sum(1 for r in self._history if r.passed)
        avg_score = sum(r.overall_score for r in self._history) / total

        # Per-criterion stats
        criterion_stats: Dict[str, Dict[str, float]] = {}
        for report in self._history:
            for r in report.results:
                if r.criterion.value not in criterion_stats:
                    criterion_stats[r.criterion.value] = {"total": 0, "pass": 0, "score_sum": 0.0}
                cs = criterion_stats[r.criterion.value]
                cs["total"] += 1
                if r.outcome == EvalOutcome.PASS:
                    cs["pass"] += 1
                cs["score_sum"] += r.score

        for cs in criterion_stats.values():
            cs["avg_score"] = round(cs["score_sum"] / cs["total"], 3)
            cs["pass_rate"] = round(cs["pass"] / cs["total"], 3)
            del cs["score_sum"]

        return {
            "total_evals": total,
            "pass_count": passed,
            "pass_rate": round(passed / total, 3),
            "avg_score": round(avg_score, 3),
            "by_criterion": criterion_stats,
        }

    def recent_reports(self, n: int = 10) -> List[dict]:
        """Get the most recent evaluation reports."""
        return [r.to_dict() for r in self._history[-n:]]

    def clear_history(self) -> None:
        """Clear evaluation history."""
        self._history.clear()


# ---- Built-in check functions ----

def check_no_empty_response(
    user_message: str,
    agent_response: str,
    context: Dict,
) -> EvalOutcome:
    """Check that the response is not empty or whitespace-only."""
    if not agent_response or not agent_response.strip():
        return EvalOutcome.FAIL
    if len(agent_response.strip()) < 5:
        return EvalOutcome.PARTIAL
    return EvalOutcome.PASS


def check_length_reasonable(
    user_message: str,
    agent_response: str,
    context: Dict,
) -> EvalOutcome:
    """Check that the response length is reasonable."""
    max_chars = context.get("max_response_chars", 4000)
    if len(agent_response) > max_chars:
        return EvalOutcome.FAIL
    if len(agent_response) > max_chars * 0.8:
        return EvalOutcome.PARTIAL
    return EvalOutcome.PASS


def check_no_forbidden_phrases(
    user_message: str,
    agent_response: str,
    context: Dict,
) -> EvalOutcome:
    """Check that the response doesn't contain forbidden phrases."""
    forbidden = context.get("forbidden_phrases", [
        "I'm just an AI",
        "As a language model",
        "I cannot",
    ])
    lower = agent_response.lower()
    for phrase in forbidden:
        if phrase.lower() in lower:
            return EvalOutcome.FAIL
    return EvalOutcome.PASS
