"""
AGENTS.md importer/exporter — the project-level half of the markdown gateway.

``AGENTS.md`` (https://agents.md) is an open convention for giving coding
agents project-level instructions. Unlike SKILL.md it has no mandatory
frontmatter, so the importer is intentionally lenient:

* Optional YAML frontmatter (``name`` / ``description`` / ``license`` /
  ``allowed-tools`` are accepted; anything else lands in ``extras``).
* ``name`` falls back to the first H1 heading, then to the file stem.
* ``description`` falls back to the first non-heading prose paragraph.
* H2 sections are extracted into ``tree.sections`` as a structured,
  project-level configuration (``"## Build commands"`` -> ``build_commands``).

Usage::

    from agentconfig.gateway import parse_agents_md, render_agents_md

    tree = parse_agents_md(Path("AGENTS.md").read_text(encoding="utf-8"))
    md = render_agents_md(tree)  # round-trip safe
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

import yaml

from .tree import AGENTS, FRONTMATTER_RE, ConfigTree, GatewayParseError

_H1_RE = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+?)\s*#*\s*$", re.MULTILINE)
_HEADING_LINE_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)
# Blocks starting with these are prose-unfriendly for a description fallback.
_NON_PROSE_RE = re.compile(r"^(?:[-*+]\s|\d+[.)]\s|>\s|\|)", re.MULTILINE)

# Keys consumed by this importer; everything else is kept in tree.extras.
_KNOWN_KEYS = ("name", "description", "license", "allowed-tools", "allowed_tools")


# ── Import (AGENTS.md -> ConfigTree) ────────────────────────────────────

def parse_agents_md(text: str, *, source: str = "AGENTS.md") -> ConfigTree:
    """
    Parse an AGENTS.md document into a project-level :class:`ConfigTree`.

    Raises:
        GatewayParseError: when the file is empty or the (optional)
            frontmatter is invalid YAML / not a mapping.
    """
    if not text.strip():
        raise GatewayParseError(
            f"{source}: file is empty; there is nothing to import."
        )

    match = FRONTMATTER_RE.match(text)
    meta: Dict[str, Any] = {}
    has_frontmatter = match is not None
    body = text
    if match:
        meta = _load_frontmatter(match.group(1), source)
        body = text[match.end():].lstrip("\r\n")

    name = _string_field(meta, "name", source) or _first_heading(body) or source.rsplit(".", 1)[0]
    description = _string_field(meta, "description", source) or _first_paragraph(body)

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

    return ConfigTree(
        kind=AGENTS,
        name=name,
        description=description,
        license=license_value,
        allowed_tools=_parse_allowed_tools(meta, source),
        body=body,
        sections=_extract_sections(body),
        extras=extras,
        has_frontmatter=has_frontmatter,
    )


def _load_frontmatter(raw_yaml: str, source: str) -> Dict[str, Any]:
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


def _first_heading(body: str) -> str:
    match = _H1_RE.search(body)
    return match.group(1).strip() if match else ""


def _first_paragraph(body: str) -> str:
    """First non-heading, non-list prose paragraph — description fallback."""
    for block in re.split(r"\n\s*\n", body):
        candidate = block.strip()
        if not candidate:
            continue
        if _HEADING_LINE_RE.match(candidate):
            continue
        if _NON_PROSE_RE.match(candidate):
            continue
        return candidate.replace("\n", " ").strip()
    return ""


def _extract_sections(body: str) -> Dict[str, str]:
    """Extract H2 sections as ``slug -> content`` (project-level config)."""
    sections: Dict[str, str] = {}
    matches = list(_H2_RE.finditer(body))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        heading = _slugify(match.group(1))
        content = body[match.end():end].strip()
        if heading and heading not in sections:
            sections[heading] = content
    return sections


def _slugify(heading: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", heading.strip().lower()).strip("_")
    return slug


# ── Export (ConfigTree -> AGENTS.md) ────────────────────────────────────

def render_agents_md(tree: ConfigTree) -> str:
    """
    Render a config tree as an AGENTS.md document.

    The frontmatter block is emitted only when the source carried one
    (``has_frontmatter``) and at least one field is present. Otherwise the
    body is emitted verbatim, which keeps round-trips lossless for plain
    AGENTS.md files.
    """
    if not tree.has_frontmatter:
        md = tree.body
        if not md.endswith("\n"):
            md += "\n"
        return md

    frontmatter: Dict[str, Any] = {}
    if tree.name:
        frontmatter["name"] = tree.name
    if tree.description:
        frontmatter["description"] = tree.description
    if tree.license:
        frontmatter["license"] = tree.license
    if tree.allowed_tools:
        frontmatter["allowed-tools"] = ", ".join(tree.allowed_tools)
    for key, value in tree.extras.items():
        if key not in _KNOWN_KEYS:
            frontmatter[key] = value

    if not frontmatter:
        md = tree.body
        if not md.endswith("\n"):
            md += "\n"
        return md

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
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return text.strip()
