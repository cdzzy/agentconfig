"""
Organization / team configuration sharing.

A deployment rarely configures every agent from scratch. Policies are decided
at the organization level, refined per team, and only then specialized per
agent. This module composes those layers into one effective config, with merge
rules that make **restriction monotonic**: a lower layer can tighten a parent's
policy but can never loosen it.

Precedence: ``organization`` → ``team`` → ``agent`` (later wins).

    from agentconfig.org import LayeredConfigResolver

    resolver = (
        LayeredConfigResolver()
        .add_file("org.yaml", "organization")
        .add_file("team.yaml", "team")
        .add_file("agent.yaml", "agent")
    )

    config = resolver.resolve_config()   # AgentConfig
    print(resolver.explain())            # which layer set which value

Usage from a directory tree::

    resolver = LayeredConfigResolver.from_directory("configs/")
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agentconfig.semantic.config_gen import AgentConfig

# ── Layers ───────────────────────────────────────────────────────────────

#: Layer levels in precedence order (lowest first).
LAYER_LEVELS = ("organization", "team", "agent")


@dataclass
class ConfigLayer:
    """
    One level of configuration.

    ``data`` is a plain dict in the same shape as ``AgentConfig.to_dict()``,
    so layers can come from a file, from an already-built ``AgentConfig``, or
    from code.
    """

    name: str
    level: str
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.level not in LAYER_LEVELS:
            raise ValueError(
                f"Unknown layer level {self.level!r}. Use one of {LAYER_LEVELS}."
            )

    @classmethod
    def from_dict(cls, data: Dict[str, Any], level: str, name: Optional[str] = None) -> "ConfigLayer":
        """Build a layer from a raw config dict."""
        return cls(name=name or str(data.get("name") or level), level=level, data=dict(data))

    @classmethod
    def from_config(cls, config: AgentConfig, level: str, name: Optional[str] = None) -> "ConfigLayer":
        """Build a layer from an :class:`AgentConfig`."""
        return cls(name=name or config.name, level=level, data=config.to_dict())

    @classmethod
    def from_file(cls, path: str, level: str, name: Optional[str] = None) -> "ConfigLayer":
        """
        Load a layer from a JSON/YAML/TOML config file.

        Uses :func:`agentconfig.loader.load_raw_dict` rather than
        ``load_config`` so the layer carries only the keys the file actually
        declares. Going through ``AgentConfig`` would backfill defaults
        (``name='My Agent'``, ``max_turns=20``, ...) and a sparse team layer
        would then override the organization's real values.
        """
        from agentconfig.loader import load_raw_dict

        return cls(name=name or path, level=level, data=load_raw_dict(path))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ConfigLayer(name={self.name!r}, level={self.level!r}, keys={sorted(self.data)})"


# ── Merge rules ──────────────────────────────────────────────────────────

#: Fields where a child layer must not be able to widen the parent's policy.
RESTRICTIVE_UNION_FIELDS = ("tools_disabled",)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge ``override`` on top of ``base``.

    Dicts merge key by key, everything else (scalars, lists) is replaced by
    the override. Returns a new dict; neither input is mutated.
    """
    result = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def merge_constraints(
    base: List[Dict[str, Any]],
    override: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Merge constraint lists by ``id``.

    A parent's constraints survive inheritance — an agent cannot silently drop
    an organization-wide guardrail by omitting it. If the child defines a
    constraint with the same ``id``, the child's version wins (so a team can
    tighten a rule but the id keeps the audit trail intact).
    """
    merged: List[Dict[str, Any]] = []
    seen: Dict[str, int] = {}

    for item in list(base) + list(override):
        if not isinstance(item, dict):
            merged.append(item)
            continue
        key = str(item.get("id", "")) or f"__anon_{len(merged)}"
        if key in seen:
            merged[seen[key]] = copy.deepcopy(item)
        else:
            seen[key] = len(merged)
            merged.append(copy.deepcopy(item))
    return merged


def merge_config_data(
    base: Dict[str, Any],
    override: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge two config layers using AgentConfig-aware rules.

    On top of a plain {@link deep_merge}:

    * ``constraints`` merge by ``id`` instead of being replaced, so inherited
      guardrails cannot be dropped.
    * ``tools_disabled`` takes the union, so a child cannot re-enable a tool the
      parent blocked.
    * ``tools_enabled`` intersects with the parent when the parent declares an
      allowlist, so a child can only narrow (never widen) the tool surface.
    """
    merged = deep_merge(base, override)

    base_constraints = [c for c in (base.get("constraints") or []) if isinstance(c, dict)]
    override_constraints = [c for c in (override.get("constraints") or []) if isinstance(c, dict)]
    if base_constraints or override_constraints:
        merged["constraints"] = merge_constraints(base_constraints, override_constraints)

    for name in RESTRICTIVE_UNION_FIELDS:
        base_values = set(base.get(name) or [])
        override_values = set(override.get(name) or [])
        if base_values or override_values:
            merged[name] = sorted(base_values | override_values)

    base_enabled = base.get("tools_enabled")
    override_enabled = override.get("tools_enabled")
    if base_enabled:
        # Parent allowlist exists: child is confined to it.
        candidate = override_enabled if override_enabled is not None else base_enabled
        merged["tools_enabled"] = sorted(set(base_enabled) & set(candidate))
    elif override_enabled is not None:
        merged["tools_enabled"] = list(override_enabled)

    return merged


# ── Resolver ─────────────────────────────────────────────────────────────


class LayeredConfigResolver:
    """
    Compose organization / team / agent config layers into one effective
    config.

    Layers are ordered by level (``organization`` < ``team`` < ``agent``); two
    layers of the same level are applied in insertion order, so the last one
    wins.
    """

    def __init__(self) -> None:
        self._layers: List[ConfigLayer] = []

    # -- construction ----------------------------------------------------

    def add(self, layer: ConfigLayer) -> "LayeredConfigResolver":
        """Add a prebuilt layer. Returns ``self`` for chaining."""
        self._layers.append(layer)
        return self

    def add_dict(
        self,
        data: Dict[str, Any],
        level: str,
        name: Optional[str] = None,
    ) -> "LayeredConfigResolver":
        """Add a raw config dict as a layer."""
        return self.add(ConfigLayer.from_dict(data, level, name=name))

    def add_config(
        self,
        config: AgentConfig,
        level: str,
        name: Optional[str] = None,
    ) -> "LayeredConfigResolver":
        """Add an :class:`AgentConfig` as a layer."""
        return self.add(ConfigLayer.from_config(config, level, name=name))

    def add_file(
        self,
        path: str,
        level: str,
        name: Optional[str] = None,
    ) -> "LayeredConfigResolver":
        """Load a config file (JSON/YAML/TOML) as a layer."""
        return self.add(ConfigLayer.from_file(path, level, name=name))

    @classmethod
    def from_directory(
        cls,
        directory: str,
        filenames: Optional[Dict[str, str]] = None,
    ) -> "LayeredConfigResolver":
        """
        Build a resolver from a directory of layered config files.

        Args:
            directory: Directory to read from.
            filenames: Optional mapping of level → filename. Defaults to
                ``organization.yaml``, ``team.yaml``, ``agent.yaml``. Missing
                files are skipped, so a deployment can define only the layers
                it actually uses.

        Example::

            resolver = LayeredConfigResolver.from_directory("configs/")
        """
        resolver = cls()
        mapping = filenames or {
            "organization": "organization.yaml",
            "team": "team.yaml",
            "agent": "agent.yaml",
        }
        for level, filename in mapping.items():
            import os

            path = os.path.join(directory, filename)
            if os.path.exists(path):
                resolver.add_file(path, level)
        return resolver

    # -- resolution ------------------------------------------------------

    def layers(self) -> List[ConfigLayer]:
        """Layers ordered by precedence (lowest first)."""
        order = {level: index for index, level in enumerate(LAYER_LEVELS)}
        return sorted(self._layers, key=lambda layer: order[layer.level])

    def resolve(self) -> Dict[str, Any]:
        """
        Merge every layer into one effective config dict.

        Returns an empty dict when no layers were added.
        """
        merged: Dict[str, Any] = {}
        for layer in self.layers():
            merged = merge_config_data(merged, layer.data)
        return merged

    def resolve_config(self) -> AgentConfig:
        """
        Resolve to a validated :class:`AgentConfig`.

        Raises:
            ValueError: when no layers were added, or when the merged result
                fails schema validation (the error list is included).
        """
        from agentconfig.semantic.config_gen import AgentConfig as _AgentConfig
        from agentconfig.validation import validate_dict

        data = self.resolve()
        if not data:
            raise ValueError("No configuration layers were added — nothing to resolve.")

        result = validate_dict(data)
        if not result.valid:
            raise ValueError(
                "Resolved configuration failed validation:\n"
                + "\n".join(f"  - {err}" for err in result.errors)
            )
        return _AgentConfig.from_dict(data)

    def explain(self) -> Dict[str, Any]:
        """
        Report which layer set each top-level field, plus the effective value.

        Useful for auditing a resolved configuration: it answers "where did
        this value come from?" without diffing files by hand.

        Example::

            {
              "model": {"source": "team", "layers": ["organization", "team"]},
              "tools_enabled": {"source": "agent", "layers": [...]},
            }
        """
        order = {level: index for index, level in enumerate(LAYER_LEVELS)}
        provenance: Dict[str, Dict[str, Any]] = {}

        for layer in self.layers():
            for key in layer.data:
                entry = provenance.setdefault(key, {"layers": [], "source": None})
                if layer.level not in entry["layers"]:
                    entry["layers"].append(layer.level)
                if entry["source"] is None or order[layer.level] > order[entry["source"]]:
                    entry["source"] = layer.level

        effective = self.resolve()
        for key, entry in provenance.items():
            entry["value"] = effective.get(key)
        return provenance

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        levels = [layer.level for layer in self.layers()]
        return f"LayeredConfigResolver(layers={levels})"


__all__ = [
    "LAYER_LEVELS",
    "ConfigLayer",
    "LayeredConfigResolver",
    "deep_merge",
    "merge_constraints",
    "merge_config_data",
]
