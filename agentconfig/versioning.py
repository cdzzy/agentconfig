"""
Config Versioning — version control and diffing for agent configurations.

Brings DevOps best practices (audit trail, rollback, diffing) to AI agent
configuration management.

Usage::

    from agentconfig.versioning import ConfigVersionManager, diff_configs
    from agentconfig.semantic.config_gen import AgentConfig

    manager = ConfigVersionManager()
    manager.commit(AgentConfig(name="My Agent"), "Initial setup")
    manager.commit(AgentConfig(name="My Agent", max_turns=30), "Bumped max turns")

    for v in manager.history():
        print(v.id, v.message)

    diff = manager.diff("v1", "v2")
    rolled_back = manager.rollback("v1")
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agentconfig.semantic.config_gen import AgentConfig


@dataclass
class ConfigVersion:
    """A single snapshot of an AgentConfig in the version history."""

    id: str
    message: str
    timestamp: str
    snapshot: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "message": self.message,
            "timestamp": self.timestamp,
        }

    def to_config(self) -> AgentConfig:
        """Reconstruct the AgentConfig from this snapshot."""
        return AgentConfig.from_dict(self.snapshot)

    def __repr__(self) -> str:  # pragma: no cover - convenience only
        return f"ConfigVersion(id={self.id!r}, message={self.message!r})"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Auto-generated fields that change on every instantiation and are therefore
# not meaningful to show in a config diff.
VOLATILE_FIELDS = frozenset({"config_id", "created_at"})


def _strip_volatile(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if k not in VOLATILE_FIELDS}


def diff_dicts(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute a structured diff between two config dicts.

    Volatile auto-generated fields (``config_id``, ``created_at``) are
    excluded so diffs reflect meaningful changes only.

    Returns a dict with ``added``, ``removed``, and ``changed`` keys.
    """
    old = _strip_volatile(old)
    new = _strip_volatile(new)
    old_keys = set(old.keys())
    new_keys = set(new.keys())

    added = {k: new[k] for k in sorted(new_keys - old_keys)}
    removed = {k: old[k] for k in sorted(old_keys - new_keys)}
    changed = {
        k: {"from": old[k], "to": new[k]}
        for k in sorted(old_keys & new_keys)
        if old[k] != new[k]
    }

    return {"added": added, "removed": removed, "changed": changed}


def diff_configs(
    old: Dict[str, Any],
    new: Dict[str, Any],
    from_label: str = "old",
    to_label: str = "new",
) -> str:
    """
    Produce a unified diff between two config dicts (JSON rendered).

    Returns:
        A unified diff string (empty if the configs are identical).
    """
    old = _strip_volatile(old)
    new = _strip_volatile(new)
    old_json = json.dumps(old, indent=2, ensure_ascii=False, sort_keys=True).splitlines()
    new_json = json.dumps(new, indent=2, ensure_ascii=False, sort_keys=True).splitlines()
    diff = difflib.unified_diff(
        old_json,
        new_json,
        fromfile=from_label,
        tofile=to_label,
        lineterm="",
    )
    return "\n".join(diff)


class ConfigVersionManager:
    """
    In-memory version control for AgentConfig instances.

    Provides commit, history, diff, and rollback operations so config changes
    can be tracked, compared, and reverted — mirroring Git workflows without
    requiring a repository.

    Example::

        manager = ConfigVersionManager()
        manager.commit(config, "Initial setup")
        manager.commit(updated, "Added web-search tool")
        print(manager.diff("v1", "v2"))
        older = manager.rollback("v1")
    """

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._versions: List[ConfigVersion] = []

    # ── Properties ────────────────────────────────────────────────────

    @property
    def current(self) -> Optional[ConfigVersion]:
        """The most recent version, or None if no commits exist."""
        return self._versions[-1] if self._versions else None

    # ── Core operations ───────────────────────────────────────────────

    def commit(self, config: AgentConfig, message: str = "") -> ConfigVersion:
        """
        Snapshot a config and append it to the history.

        Args:
            config: AgentConfig instance to snapshot.
            message: Human-readable description of the change.

        Returns:
            The created ConfigVersion.
        """
        version = ConfigVersion(
            id=f"v{len(self._versions) + 1}",
            message=message,
            timestamp=_now(),
            snapshot=config.to_dict(),
        )
        self._versions.append(version)
        return version

    def history(self) -> List[ConfigVersion]:
        """Return the full version history (oldest first)."""
        return list(self._versions)

    def get(self, version_id: str) -> Optional[ConfigVersion]:
        """Look up a version by its id (e.g. ``v2``)."""
        for v in self._versions:
            if v.id == version_id:
                return v
        return None

    def rollback(self, version_id: str) -> AgentConfig:
        """
        Reconstruct the AgentConfig at the given version id.

        Args:
            version_id: The version id to roll back to.

        Returns:
            A new AgentConfig matching the requested snapshot.

        Raises:
            ValueError: If the version id is unknown.
        """
        version = self.get(version_id)
        if version is None:
            raise ValueError(
                f"Unknown version: {version_id}. "
                f"Available: {[v.id for v in self._versions]}"
            )
        return version.to_config()

    def diff(self, v1: str, v2: str) -> str:
        """
        Compute a unified diff between two versions.

        Args:
            v1: The "old" version id.
            v2: The "new" version id.

        Returns:
            A unified diff string.

        Raises:
            ValueError: If either version id is unknown.
        """
        old = self.get(v1)
        new = self.get(v2)
        if old is None or new is None:
            missing = [v for v in (v1, v2) if self.get(v) is None]
            raise ValueError(
                f"Unknown version(s): {missing}. "
                f"Available: {[v.id for v in self._versions]}"
            )
        return diff_configs(old.snapshot, new.snapshot, from_label=v1, to_label=v2)

    def diff_to_current(self, version_id: str) -> str:
        """Diff a historical version against the latest committed version."""
        if self.current is None:
            raise ValueError("No commits exist yet.")
        return self.diff(version_id, self.current.id)

    def structured_diff(self, v1: str, v2: str) -> Dict[str, Any]:
        """Compute a structured (added/removed/changed) diff between two versions."""
        old = self.get(v1)
        new = self.get(v2)
        if old is None or new is None:
            raise ValueError(f"Unknown version(s): {v1}, {v2}")
        return diff_dicts(old.snapshot, new.snapshot)

    def __len__(self) -> int:
        return len(self._versions)
