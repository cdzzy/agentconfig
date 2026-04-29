"""
AgentMonitor — in-memory monitoring store for agent run records.

Provides aggregated stats for the dashboard:
- Total runs, success/error/escalation counts
- Average latency, tokens, turn count
- Constraint violation frequency
- Recent run history
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import List, Optional, Dict, Any
import threading

from agentconfig.runtime.executor import RunRecord, RunStatus


class AgentMonitor:
    """
    Thread-safe in-memory store for RunRecord objects.

    Usage::

        monitor = AgentMonitor()
        monitor.record(run_record)
        stats = monitor.stats()
        recent = monitor.recent(n=20)
    """

    def __init__(self, max_records: int = 10000):
        self._records: List[RunRecord] = []
        self._lock = threading.Lock()
        self._max = max_records

    # ------------------------------------------------------------------
    def record(self, run: RunRecord) -> None:
        with self._lock:
            self._records.append(run)
            if len(self._records) > self._max:
                self._records = self._records[-self._max:]

    def recent(self, n: int = 50, agent_name: Optional[str] = None) -> List[dict]:
        with self._lock:
            records = list(self._records)

        if agent_name:
            records = [r for r in records if r.agent_name == agent_name]

        records.sort(key=lambda r: r.started_at, reverse=True)
        return [r.to_dict() for r in records[:n]]

    def stats(self, agent_name: Optional[str] = None) -> dict:
        with self._lock:
            records = list(self._records)

        if agent_name:
            records = [r for r in records if r.agent_name == agent_name]

        if not records:
            return self._empty_stats()

        total = len(records)
        by_status: Dict[str, int] = defaultdict(int)
        for r in records:
            by_status[r.status.value] += 1

        completed = [r for r in records if r.status == RunStatus.COMPLETED]
        avg_latency = (
            sum(r.total_latency_ms for r in completed) / len(completed)
            if completed else 0.0
        )
        avg_turns = (
            sum(r.turn_count for r in completed) / len(completed)
            if completed else 0.0
        )
        total_violations = sum(r.violation_count for r in records)

        # Violation breakdown by type
        violation_types: Dict[str, int] = defaultdict(int)
        for r in records:
            for turn in r.turns:
                for v in turn.constraint_violations:
                    violation_types[v.get("type", "unknown")] += 1

        # Per-agent stats
        agents: Dict[str, dict] = defaultdict(lambda: {
            "total": 0, "completed": 0, "escalated": 0, "errors": 0, "violations": 0
        })
        for r in records:
            a = agents[r.agent_name]
            a["total"] += 1
            if r.status == RunStatus.COMPLETED:
                a["completed"] += 1
            elif r.status == RunStatus.ESCALATED:
                a["escalated"] += 1
            elif r.status == RunStatus.ERROR:
                a["errors"] += 1
            a["violations"] += r.violation_count

        return {
            "total_runs":        total,
            "by_status":         dict(by_status),
            "avg_latency_ms":    round(avg_latency, 1),
            "avg_turns":         round(avg_turns, 1),
            "total_violations":  total_violations,
            "violation_by_type": dict(violation_types),
            "agents":            dict(agents),
        }

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    @staticmethod
    def _empty_stats() -> dict:
        return {
            "total_runs": 0,
            "by_status": {},
            "avg_latency_ms": 0.0,
            "avg_turns": 0.0,
            "total_violations": 0,
            "violation_by_type": {},
            "agents": {},
        }
