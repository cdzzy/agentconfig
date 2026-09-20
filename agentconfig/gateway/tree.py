"""
Gateway config tree — the unified intermediate representation ("config tree")
shared by the SKILL.md and AGENTS.md importers/exporters.

Both importers produce a :class:`ConfigTree`; both exporters consume one.
Round-trip guarantee::

    parse_skill_md(render_skill_md(parse_skill_md(x))) == parse_skill_md(x)

Unknown frontmatter keys are preserved (in insertion order) inside ``extras``
so that importing and re-exporting does not silently drop metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── Kinds ───────────────────────────────────────────────────────────────

SKILL = "skill"
AGENTS = "agents"
VALID_KINDS = (SKILL, AGENTS)

# YAML frontmatter block: must start at byte 0 with a "---" fence line and
# end with a closing "---" fence line. Shared by SKILL.md and AGENTS.md.
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)


# ── Errors ──────────────────────────────────────────────────────────────

class GatewayError(Exception):
    """Base class for all SKILL.md / AGENTS.md gateway errors."""


class GatewayParseError(GatewayError):
    """Raised when a markdown source file is malformed and cannot be parsed."""


class GatewayValidationError(GatewayError):
    """Raised when a config tree cannot be rendered into a compliant file."""


# ── Config tree ─────────────────────────────────────────────────────────

@dataclass
class ConfigTree:
    """
    Unified intermediate representation for the markdown gateway.

    Attributes:
        kind:            ``"skill"`` (SKILL.md) or ``"agents"`` (AGENTS.md).
        name:            Skill / project name (frontmatter, else derived).
        description:     Short description (frontmatter, else derived).
        license:         Optional license identifier (e.g. ``"MIT"``).
        allowed_tools:   Optional allow-list of tool names.
        body:            Markdown body (everything after the frontmatter).
        sections:        Optional H2 sections (AGENTS.md project-level config).
        extras:          Unknown frontmatter keys, insertion order preserved.
        has_frontmatter: Whether the parsed source carried a YAML frontmatter.
    """

    kind: str
    name: str = ""
    description: str = ""
    license: Optional[str] = None
    allowed_tools: List[str] = field(default_factory=list)
    body: str = ""
    sections: Dict[str, str] = field(default_factory=dict)
    extras: Dict[str, Any] = field(default_factory=dict)
    has_frontmatter: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the tree to a JSON-compatible dict."""
        return {
            "kind": self.kind,
            "name": self.name,
            "description": self.description,
            "license": self.license,
            "allowed_tools": list(self.allowed_tools),
            "body": self.body,
            "sections": dict(self.sections),
            "extras": self.extras,
            "has_frontmatter": self.has_frontmatter,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "ConfigTree":
        """Rebuild a tree from :meth:`to_dict` output with clear validation."""
        if not isinstance(data, dict):
            raise GatewayValidationError(
                f"config tree must be a JSON object, got {type(data).__name__}"
            )
        kind = data.get("kind")
        if kind not in VALID_KINDS:
            raise GatewayValidationError(
                f"unknown config tree kind {kind!r}; expected one of {list(VALID_KINDS)}. "
                f"Was this file produced by 'agentconfig skill import'?"
            )
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            raise GatewayValidationError(
                f"config tree has unexpected fields: {', '.join(sorted(unknown))}"
            )
        license_value = data.get("license")
        if license_value is not None and not isinstance(license_value, str):
            raise GatewayValidationError("config tree field 'license' must be a string or null")
        allowed = data.get("allowed_tools", [])
        if not isinstance(allowed, list) or not all(isinstance(t, str) for t in allowed):
            raise GatewayValidationError("config tree field 'allowed_tools' must be a list of strings")
        extras = data.get("extras", {})
        if not isinstance(extras, dict):
            raise GatewayValidationError("config tree field 'extras' must be an object")
        sections = data.get("sections", {})
        if not isinstance(sections, dict):
            raise GatewayValidationError("config tree field 'sections' must be an object")
        return cls(
            kind=kind,
            name=data.get("name", ""),
            description=data.get("description", ""),
            license=license_value,
            allowed_tools=list(allowed),
            body=data.get("body", ""),
            sections=dict(sections),
            extras=dict(extras),
            has_frontmatter=bool(data.get("has_frontmatter", False)),
        )

    def to_agent_config_dict(self) -> Dict[str, Any]:
        """
        Map the tree onto an AgentConfig-compatible dict that can be consumed
        by ``agentconfig.semantic.config_gen.AgentConfig.from_dict``. This is
        the bridge from markdown gateway into the AgentConfig core.
        """
        system_prompt = self.body.strip()
        if self.kind == SKILL:
            if self.description:
                system_prompt = f"{self.description}\n\n{system_prompt}".strip()
        metadata: Dict[str, Any] = {
            "source": f"gateway:{self.kind}",
            "extras": self.extras,
            "sections": self.sections,
        }
        if self.license:
            metadata["license"] = self.license
        return {
            "name": self.name or "Imported Agent",
            "description": self.description,
            "system_prompt": system_prompt,
            "tools_enabled": list(self.allowed_tools),
            "metadata": metadata,
        }
