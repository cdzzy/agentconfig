"""
SKILL.md importer/exporter — one half of the markdown gateway.

Import side (SKILL.md -> ConfigTree) follows the Anthropic Agent Skills
convention: a YAML frontmatter block with ``name`` / ``description`` (both
required), optional ``license`` and ``allowed-tools``, followed by the
Markdown skill body.

Export side (ConfigTree -> SKILL.md) re-serializes the frontmatter and runs
required-field validation so that only compliant SKILL.md files are written.

Usage::

    from agentconfig.gateway import parse_skill_md, render_skill_md

    tree = parse_skill_md(Path("SKILL.md").read_text(encoding="utf-8"))
    md = render_skill_md(tree)  # round-trip safe
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

import yaml

from .tree import FRONTMATTER_RE, SKILL, ConfigTree, GatewayParseError, GatewayValidationError

# Skill name per the Agent Skills spec: lowercase letters, digits and
# hyphens, 1-64 characters, must start and end with an alphanumeric char.
SKILL_NAME_RE = re.compile(r"^[a-z0-9](?:-?[a-z0-9]){0,63}$")

MAX_DESCRIPTION_LEN = 1024

# Keys consumed by this importer; everything else is kept in tree.extras.
_KNOWN_KEYS = ("name", "description", "license", "allowed-tools", "allowed_tools")


# ── Import (SKILL.md -> ConfigTree) ─────────────────────────────────────

def parse_skill_md(text: str, *, source: str = "SKILL.md") -> ConfigTree:
    """
    Parse a SKILL.md document into a :class:`ConfigTree`.

    Raises:
        GatewayParseError: with a clear, actionable message when the input is
            malformed (missing frontmatter, invalid YAML, non-mapping
            frontmatter, or missing required ``name``/``description``).
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise GatewayParseError(
            f"{source}: missing YAML frontmatter. A SKILL.md must start with a "
            f"'---' line, then a YAML mapping containing at least 'name' and "
            f"'description', then a closing '---' line before the Markdown body."
        )

    meta = _load_frontmatter(match.group(1), source)

    name = _string_field(meta, "name", source)
    description = _string_field(meta, "description", source)
    if not name:
        raise GatewayParseError(
            f"{source}: required frontmatter field 'name' is missing or empty."
        )
    if not description:
        raise GatewayParseError(
            f"{source}: required frontmatter field 'description' is missing or empty."
        )

    license_value = meta.get("license")
    if license_value is not None and not isinstance(license_value, str):
        raise GatewayParseError(
            f"{source}: frontmatter field 'license' must be a string, "
            f"got {type(license_value).__name__}."
        )

    extras: Dict[str, Any] = {}
    for key, value in meta.items():
        if key not in _KNOWN_KEYS:
            extras[key] = value

    body = text[match.end():].lstrip("\r\n")

    return ConfigTree(
        kind=SKILL,
        name=name,
        description=description,
        license=license_value,
        allowed_tools=_parse_allowed_tools(meta, source),
        body=body,
        extras=extras,
        has_frontmatter=True,
    )


def _load_frontmatter(raw_yaml: str, source: str) -> Dict[str, Any]:
    """Safely load the frontmatter YAML, raising clear errors on failure."""
    try:
        meta = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise GatewayParseError(
            f"{source}: invalid YAML in frontmatter: {_first_line(str(exc))}"
        ) from exc
    if not isinstance(meta, dict):
        raise GatewayParseError(
            f"{source}: frontmatter must be a YAML mapping (key: value lines), "
            f"got {type(meta).__name__}."
        )
    return meta


def _string_field(meta: Dict[str, Any], key: str, source: str) -> str:
    """Extract a string frontmatter field; scalars are stringified."""
    value = meta.get(key)
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    raise GatewayParseError(
        f"{source}: frontmatter field '{key}' must be a string, "
        f"got {type(value).__name__}."
    )


def _parse_allowed_tools(meta: Dict[str, Any], source: str) -> List[str]:
    """Parse ``allowed-tools`` (comma-separated string or list of strings)."""
    raw = meta.get("allowed-tools")
    if raw is None:
        raw = meta.get("allowed_tools")
    if raw is None:
        return []
    if isinstance(raw, str):
        return [tool.strip() for tool in raw.split(",") if tool.strip()]
    if isinstance(raw, list):
        tools: List[str] = []
        for item in raw:
            if not isinstance(item, str):
                raise GatewayParseError(
                    f"{source}: frontmatter field 'allowed-tools' must contain "
                    f"only strings, got {type(item).__name__} inside the list."
                )
            if item.strip():
                tools.append(item.strip())
        return tools
    raise GatewayParseError(
        f"{source}: frontmatter field 'allowed-tools' must be a comma-separated "
        f"string or a list of strings, got {type(raw).__name__}."
    )


# ── Validation + Export (ConfigTree -> SKILL.md) ────────────────────────

def validate_skill_tree(tree: ConfigTree) -> List[str]:
    """
    Validate that a config tree can be rendered as a compliant SKILL.md.

    Returns a list of human-readable problems (empty when valid).
    """
    errors: List[str] = []
    if not tree.name or not tree.name.strip():
        errors.append("frontmatter field 'name' is required and cannot be empty")
    if not tree.description or not tree.description.strip():
        errors.append("frontmatter field 'description' is required and cannot be empty")
    if tree.name and not SKILL_NAME_RE.match(tree.name):
        errors.append(
            f"invalid skill name '{tree.name}': use lowercase letters, digits and "
            f"hyphens (max 64 chars), e.g. 'pdf-report'"
        )
    if tree.description and len(tree.description) > MAX_DESCRIPTION_LEN:
        errors.append(
            f"frontmatter field 'description' is {len(tree.description)} characters; "
            f"the limit is {MAX_DESCRIPTION_LEN}"
        )
    return errors


def render_skill_md(tree: ConfigTree, *, strict: bool = True) -> str:
    """
    Render a config tree as a compliant SKILL.md document.

    Args:
        tree:   Config tree (usually with ``kind == "skill"``).
        strict: When True (default), run :func:`validate_skill_tree` and raise
                :class:`GatewayValidationError` on any problem.

    Raises:
        GatewayValidationError: when required frontmatter is missing/invalid.
    """
    if strict:
        errors = validate_skill_tree(tree)
        if errors:
            raise GatewayValidationError(
                "cannot render SKILL.md — frontmatter validation failed:\n  - "
                + "\n  - ".join(errors)
            )

    frontmatter: Dict[str, Any] = {
        "name": tree.name,
        "description": tree.description,
    }
    if tree.license:
        frontmatter["license"] = tree.license
    if tree.allowed_tools:
        frontmatter["allowed-tools"] = ", ".join(tree.allowed_tools)
    for key, value in tree.extras.items():
        if key not in _KNOWN_KEYS:
            frontmatter[key] = value

    yaml_text = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=4096,
    ).strip("\n")

    md = f"---\n{yaml_text}\n---\n"
    if tree.body:
        md += f"\n{tree.body}"
    if not md.endswith("\n"):
        md += "\n"
    return md


def _first_line(text: str) -> str:
    """Return the first non-empty line of an error string."""
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return text.strip()
