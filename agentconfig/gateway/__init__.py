"""
Markdown Gateway — bidirectional SKILL.md / AGENTS.md support.

The gateway treats Markdown documents as first-class agent configuration:
* :func:`parse_skill_md`   — SKILL.md (YAML frontmatter + Markdown body) -> ConfigTree
* :func:`render_skill_md`  — ConfigTree -> compliant SKILL.md (required-field validation)
* :func:`parse_agents_md`  — AGENTS.md (project-level instructions)    -> ConfigTree
* :func:`render_agents_md` — ConfigTree -> AGENTS.md

Round-trips are lossless at tree level::

    tree = parse_skill_md(text)
    assert parse_skill_md(render_skill_md(tree)) == tree

CLI::

    agentconfig skill import --source ./my-skill/SKILL.md --output skill.tree.json
    agentconfig skill export --config skill.tree.json --target skill --output SKILL.md
    agentconfig skill export --config skill.tree.json --target agents --output AGENTS.md
"""

from .tree import (
    AGENTS,
    SKILL,
    ConfigTree,
    GatewayError,
    GatewayParseError,
    GatewayValidationError,
)
from .skill_md import parse_skill_md, render_skill_md, validate_skill_tree
from .agents_md import parse_agents_md, render_agents_md

__all__ = [
    "AGENTS",
    "SKILL",
    "ConfigTree",
    "GatewayError",
    "GatewayParseError",
    "GatewayValidationError",
    "parse_skill_md",
    "render_skill_md",
    "validate_skill_tree",
    "parse_agents_md",
    "render_agents_md",
]
