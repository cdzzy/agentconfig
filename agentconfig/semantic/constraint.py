"""
Constraint Engine — enforces business rules on agent behavior at runtime.

Business users define constraints in plain terms:
  - "Always respond within 3 sentences"
  - "Never output prices"
  - "If user asks about legal matters, refuse and recommend a lawyer"

These are validated against each agent response before it reaches the user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Callable


class ConstraintType(str, Enum):
    FORBIDDEN_TOPIC    = "forbidden_topic"
    FORBIDDEN_KEYWORD  = "forbidden_keyword"
    MAX_LENGTH         = "max_length"
    MIN_LENGTH         = "min_length"
    REQUIRED_KEYWORD   = "required_keyword"
    TONE_CHECK         = "tone_check"
    ESCALATION         = "escalation"
    CUSTOM             = "custom"


class ConstraintAction(str, Enum):
    BLOCK    = "block"     # Block the response entirely
    WARN     = "warn"      # Log a warning but allow through
    REPLACE  = "replace"   # Replace with a safe fallback message
    ESCALATE = "escalate"  # Trigger human handoff


@dataclass
class ConstraintViolation:
    constraint_id: str
    constraint_type: ConstraintType
    message: str
    action: ConstraintAction
    matched_text: str = ""


@dataclass
class Constraint:
    """A single business rule constraint."""

    id: str
    type: ConstraintType
    description: str
    action: ConstraintAction = ConstraintAction.BLOCK
    fallback_message: str = "I'm sorry, I can't help with that. Please contact our team directly."

    # Type-specific parameters
    keywords: List[str] = field(default_factory=list)   # for FORBIDDEN/REQUIRED_KEYWORD
    pattern:  str = ""                                   # for CUSTOM (regex)
    max_chars: int = 0                                   # for MAX_LENGTH
    min_chars: int = 0                                   # for MIN_LENGTH
    check_fn: Optional[Callable[[str], bool]] = field(default=None, repr=False)  # for CUSTOM

    def check(self, text: str) -> Optional[ConstraintViolation]:
        """
        Check text against this constraint.
        Returns a ConstraintViolation if violated, else None.
        """
        text_lower = text.lower()

        if self.type == ConstraintType.FORBIDDEN_KEYWORD:
            for kw in self.keywords:
                if kw.lower() in text_lower:
                    return ConstraintViolation(
                        constraint_id=self.id,
                        constraint_type=self.type,
                        message=f"Forbidden keyword detected: '{kw}'",
                        action=self.action,
                        matched_text=kw,
                    )

        elif self.type == ConstraintType.FORBIDDEN_TOPIC:
            for kw in self.keywords:
                if kw.lower() in text_lower:
                    return ConstraintViolation(
                        constraint_id=self.id,
                        constraint_type=self.type,
                        message=f"Response touches forbidden topic: '{kw}'",
                        action=self.action,
                        matched_text=kw,
                    )

        elif self.type == ConstraintType.REQUIRED_KEYWORD:
            if not any(kw.lower() in text_lower for kw in self.keywords):
                return ConstraintViolation(
                    constraint_id=self.id,
                    constraint_type=self.type,
                    message=f"Required keyword missing. Expected one of: {self.keywords}",
                    action=self.action,
                )

        elif self.type == ConstraintType.MAX_LENGTH:
            if self.max_chars > 0 and len(text) > self.max_chars:
                return ConstraintViolation(
                    constraint_id=self.id,
                    constraint_type=self.type,
                    message=f"Response too long: {len(text)} chars > {self.max_chars} limit",
                    action=self.action,
                )

        elif self.type == ConstraintType.MIN_LENGTH:
            if self.min_chars > 0 and len(text.strip()) < self.min_chars:
                return ConstraintViolation(
                    constraint_id=self.id,
                    constraint_type=self.type,
                    message=f"Response too short: {len(text.strip())} chars < {self.min_chars} minimum",
                    action=self.action,
                )

        elif self.type == ConstraintType.ESCALATION:
            # Check if any escalation trigger keyword appears in the text
            for kw in self.keywords:
                if kw.lower() in text_lower:
                    return ConstraintViolation(
                        constraint_id=self.id,
                        constraint_type=self.type,
                        message=f"Escalation trigger detected: '{kw}'",
                        action=ConstraintAction.ESCALATE,
                        matched_text=kw,
                    )

        elif self.type == ConstraintType.TONE_CHECK:
            # Check that the response contains at least one expected tone signal keyword.
            # keywords = list of positive tone words (e.g. ["sorry", "apologize", "help"])
            # If NONE appear, it's a violation.
            if self.keywords and not any(kw.lower() in text_lower for kw in self.keywords):
                return ConstraintViolation(
                    constraint_id=self.id,
                    constraint_type=self.type,
                    message=f"Tone check failed: none of the expected signals found: {self.keywords}",
                    action=self.action,
                )

        elif self.type == ConstraintType.CUSTOM:
            if self.pattern:
                if re.search(self.pattern, text, re.IGNORECASE):
                    return ConstraintViolation(
                        constraint_id=self.id,
                        constraint_type=self.type,
                        message=f"Custom pattern matched: {self.pattern}",
                        action=self.action,
                    )
            if self.check_fn and self.check_fn(text):
                return ConstraintViolation(
                    constraint_id=self.id,
                    constraint_type=self.type,
                    message=f"Custom check failed: {self.description}",
                    action=self.action,
                )

        return None

    def to_dict(self) -> dict:
        return {
            "id":              self.id,
            "type":            self.type.value,
            "description":     self.description,
            "action":          self.action.value,
            "fallback_message": self.fallback_message,
            "keywords":        self.keywords,
            "pattern":         self.pattern,
            "max_chars":       self.max_chars,
            "min_chars":       self.min_chars,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Constraint":
        return cls(
            id=d["id"],
            type=ConstraintType(d["type"]),
            description=d.get("description", ""),
            action=ConstraintAction(d.get("action", "block")),
            fallback_message=d.get("fallback_message", "I'm sorry, I can't help with that."),
            keywords=d.get("keywords", []),
            pattern=d.get("pattern", ""),
            max_chars=d.get("max_chars", 0),
            min_chars=d.get("min_chars", 0),
        )


@dataclass
class CheckResult:
    passed: bool
    violations: List[ConstraintViolation] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return any(v.action == ConstraintAction.BLOCK for v in self.violations)

    @property
    def should_escalate(self) -> bool:
        return any(v.action == ConstraintAction.ESCALATE for v in self.violations)

    @property
    def fallback_messages(self) -> List[str]:
        return [v.constraint_id for v in self.violations if v.action == ConstraintAction.REPLACE]


class ConstraintEngine:
    """
    Validates agent responses against a set of business constraints.

    Usage::

        engine = ConstraintEngine()
        engine.add(Constraint(
            id="no-pricing",
            type=ConstraintType.FORBIDDEN_KEYWORD,
            description="Never reveal pricing information",
            keywords=["$", "price", "cost", "fee", "charge"],
            action=ConstraintAction.BLOCK,
        ))

        result = engine.check("Our premium plan costs $99/month.")
        if result.blocked:
            print("Response blocked!")
    """

    def __init__(self):
        self._constraints: List[Constraint] = []

    def add(self, constraint: Constraint) -> "ConstraintEngine":
        self._constraints.append(constraint)
        return self

    def remove(self, constraint_id: str) -> bool:
        before = len(self._constraints)
        self._constraints = [c for c in self._constraints if c.id != constraint_id]
        return len(self._constraints) < before

    def check(self, text: str) -> CheckResult:
        violations = []
        for constraint in self._constraints:
            v = constraint.check(text)
            if v:
                violations.append(v)
        return CheckResult(passed=len(violations) == 0, violations=violations)

    @property
    def constraints(self) -> List[Constraint]:
        return list(self._constraints)

    def to_list(self) -> List[dict]:
        return [c.to_dict() for c in self._constraints]

    @classmethod
    def from_list(cls, items: List[dict]) -> "ConstraintEngine":
        engine = cls()
        for item in items:
            engine.add(Constraint.from_dict(item))
        return engine
