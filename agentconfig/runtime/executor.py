"""
AgentExecutor — runs an agent using an AgentConfig.

Wraps any LLM call with constraint checking, turn limiting, audit logging,
and escalation handling. Framework-agnostic: pass your own llm_fn.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional, Callable, Dict, Any

from agentconfig.semantic.config_gen import AgentConfig
from agentconfig.semantic.constraint import ConstraintAction


class RunStatus(str, Enum):
    RUNNING   = "running"
    COMPLETED = "completed"
    BLOCKED   = "blocked"
    ESCALATED = "escalated"
    ERROR     = "error"
    TIMEOUT   = "timeout"


@dataclass
class Turn:
    role: str       # "user" or "assistant"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tokens: int = 0
    constraint_violations: List[dict] = field(default_factory=list)
    latency_ms: float = 0.0


@dataclass
class RunRecord:
    """Complete record of a single agent execution session."""
    run_id:     str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    config_id:  str = ""
    agent_name: str = ""
    status:     RunStatus = RunStatus.RUNNING
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at:   Optional[str] = None
    turns:      List[Turn] = field(default_factory=list)
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    error_message: Optional[str] = None
    escalation_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def turn_count(self) -> int:
        return len([t for t in self.turns if t.role == "user"])

    @property
    def duration_seconds(self) -> float:
        if self.ended_at:
            start = datetime.fromisoformat(self.started_at)
            end   = datetime.fromisoformat(self.ended_at)
            return (end - start).total_seconds()
        return 0.0

    @property
    def violation_count(self) -> int:
        return sum(len(t.constraint_violations) for t in self.turns)

    def to_dict(self) -> dict:
        return {
            "run_id":            self.run_id,
            "config_id":         self.config_id,
            "agent_name":        self.agent_name,
            "status":            self.status.value,
            "started_at":        self.started_at,
            "ended_at":          self.ended_at,
            "turn_count":        self.turn_count,
            "total_tokens":      self.total_tokens,
            "total_latency_ms":  self.total_latency_ms,
            "duration_seconds":  self.duration_seconds,
            "violation_count":   self.violation_count,
            "error_message":     self.error_message,
            "escalation_reason": self.escalation_reason,
            "turns": [
                {
                    "role":      t.role,
                    "content":   t.content,
                    "timestamp": t.timestamp,
                    "tokens":    t.tokens,
                    "latency_ms": t.latency_ms,
                    "violations": t.constraint_violations,
                }
                for t in self.turns
            ],
            "metadata": self.metadata,
        }


class AgentExecutor:
    """
    Executes an agent session using an AgentConfig.

    Usage::

        def my_llm(messages: list) -> str:
            # call your LLM here
            return "Hello! How can I help you?"

        executor = AgentExecutor(llm_fn=my_llm)
        response, record = executor.chat(config, user_message="Hello")
        print(response)
    """

    def __init__(self, llm_fn: Optional[Callable] = None):
        """
        Args:
            llm_fn: Callable that takes a list of {"role": ..., "content": ...}
                    messages and returns a string response.
                    If None, a mock echo function is used (for testing).
        """
        self._llm_fn = llm_fn or self._mock_llm
        self._active_sessions: Dict[str, Dict] = {}

    # ------------------------------------------------------------------
    def chat(
        self,
        config: AgentConfig,
        user_message: str,
        session_id: Optional[str] = None,
    ) -> tuple[str, RunRecord]:
        """
        Send a message and get a response, with full constraint checking.

        Returns:
            (response_text, RunRecord)
        """
        sid = session_id or str(uuid.uuid4())[:8]

        # Get or create session state
        if sid not in self._active_sessions:
            self._active_sessions[sid] = {
                "history":    [{"role": "system", "content": config.system_prompt}],
                "record":     RunRecord(
                    config_id=config.config_id,
                    agent_name=config.name,
                ),
            }

        session  = self._active_sessions[sid]
        history  = session["history"]
        record   = session["record"]
        engine   = config.get_constraint_engine()

        # Check turn limit
        if record.turn_count >= config.max_turns:
            record.status = RunStatus.COMPLETED
            record.ended_at = datetime.now(timezone.utc).isoformat()
            return "I'm sorry, we've reached the maximum conversation length. Please start a new session.", record

        # Add user turn
        history.append({"role": "user", "content": user_message})
        user_turn = Turn(role="user", content=user_message)
        record.turns.append(user_turn)

        # Call LLM
        t0 = time.time()
        try:
            raw_response = self._llm_fn(history)
        except Exception as e:
            record.status = RunStatus.ERROR
            record.error_message = str(e)
            record.ended_at = datetime.now(timezone.utc).isoformat()
            return f"An error occurred: {e}", record

        latency_ms = (time.time() - t0) * 1000

        # Constraint check
        check_result = engine.check(raw_response)
        violations_data = [
            {
                "id":      v.constraint_id,
                "type":    v.constraint_type.value,
                "message": v.message,
                "action":  v.action.value,
            }
            for v in check_result.violations
        ]

        assistant_turn = Turn(
            role="assistant",
            content=raw_response,
            latency_ms=latency_ms,
            constraint_violations=violations_data,
        )
        record.total_latency_ms += latency_ms

        if check_result.blocked:
            # Find the first blocking constraint's fallback
            fallback = "I'm sorry, I can't provide that information. Please contact our team."
            for v in check_result.violations:
                if v.action == ConstraintAction.BLOCK:
                    # Look up fallback from config constraints
                    for c in config.constraints:
                        if c.get("id") == v.constraint_id:
                            fallback = c.get("fallback_message", fallback)
                            break
                    break
            assistant_turn.content = fallback
            record.turns.append(assistant_turn)
            history.append({"role": "assistant", "content": fallback})
            return fallback, record

        if check_result.should_escalate:
            escalation_msg = "I'm transferring you to a human specialist who can better assist you."
            assistant_turn.content = escalation_msg
            record.turns.append(assistant_turn)
            record.status = RunStatus.ESCALATED
            record.escalation_reason = check_result.violations[0].message
            record.ended_at = datetime.now(timezone.utc).isoformat()
            return escalation_msg, record

        # All good
        history.append({"role": "assistant", "content": raw_response})
        record.turns.append(assistant_turn)
        return raw_response, record

    def end_session(self, session_id: str) -> Optional[RunRecord]:
        if session_id in self._active_sessions:
            record = self._active_sessions.pop(session_id)["record"]
            if record.status == RunStatus.RUNNING:
                record.status = RunStatus.COMPLETED
                record.ended_at = datetime.now(timezone.utc).isoformat()
            return record
        return None

    @staticmethod
    def _mock_llm(messages: list) -> str:
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        return f"[Mock response] You said: {last_user}"
