"""
Portable Agent Directory — .agent/ directory read/write support.

Compatible with the agentic-stack .agent/ portable directory convention
(https://github.com/codejunkie99/agentic-stack).

The .agent/ directory is a portable "brain" that can be shared across
Claude Code, Cursor, Windsurf, and other AI coding tools, so that
switching tools does not mean losing knowledge.

Directory layout::

    .agent/
    ├── config.yaml              # AgentConfig main configuration
    ├── AGENTS.md                # Navigation / overview file
    ├── harness/
    │   └── hooks/               # Dispatcher + hooks (read-only sync)
    ├── memory/
    │   ├── working/             # Working (short-term) memory
    │   ├── episodic/            # Episodic (historical logs)
    │   ├── semantic/
    │   │   ├── lessons.jsonl    # Graduated lessons (JSONL)
    │   │   └── LESSONS.md       # Rendered lessons (markdown)
    │   └── personal/
    │       └── PREFERENCES.md   # Personal preferences
    ├── skills/
    │   ├── _index.md            # Skill index
    │   ├── _manifest.jsonl      # Lightweight skill manifest (always loaded)
    │   └── <skill-name>/
    │       └── SKILL.md         # Detailed skill file (loaded on demand)
    ├── protocols/
    │   ├── permissions.md       # Permission definitions
    │   └── hook_patterns.json   # Custom high/medium risk regex patterns
    ├── tools/                   # Host agent CLI tools
    ├── data-layer/              # Local data layer (optional)
    └── flywheel/                # Data flywheel

Usage::

    from agentconfig.portable import load_agent_dir, save_agent_dir, AgentDir

    # Load AgentConfig from .agent/ directory
    config = load_agent_dir(".agent/")

    # Export AgentConfig to .agent/ directory
    save_agent_dir(config, ".agent/")

    # Object-oriented interface
    agent_dir = AgentDir(".agent/")
    config = agent_dir.load_config()
    agent_dir.save_config(config)
    skills = agent_dir.list_skills()
    lessons = agent_dir.list_lessons()
    prefs = agent_dir.load_preferences()
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentconfig.semantic.config_gen import AgentConfig


# ── Constants ───────────────────────────────────────────────────────────

AGENT_DIR_NAME = ".agent"
CONFIG_FILENAME = "config.yaml"

# Standard subdirectories
DIR_HARNESS = "harness"
DIR_MEMORY = "memory"
DIR_WORKING = "memory/working"
DIR_EPISODIC = "memory/episodic"
DIR_SEMANTIC = "memory/semantic"
DIR_PERSONAL = "memory/personal"
DIR_SKILLS = "skills"
DIR_PROTOCOLS = "protocols"
DIR_TOOLS = "tools"
DIR_DATA_LAYER = "data-layer"
DIR_FLYWHEEL = "flywheel"

# Standard files
FILE_AGENTS_MD = "AGENTS.md"
FILE_LESSONS_JSONL = "memory/semantic/lessons.jsonl"
FILE_LESSONS_MD = "memory/semantic/LESSONS.md"
FILE_PREFERENCES_MD = "memory/personal/PREFERENCES.md"
FILE_SKILL_MANIFEST = "skills/_manifest.jsonl"
FILE_SKILL_INDEX = "skills/_index.md"
FILE_PERMISSIONS_MD = "protocols/permissions.md"
FILE_HOOK_PATTERNS = "protocols/hook_patterns.json"

ALL_SUBDIRS = [
    DIR_HARNESS,
    DIR_HARNESS + "/hooks",
    DIR_MEMORY,
    DIR_WORKING,
    DIR_EPISODIC,
    DIR_SEMANTIC,
    DIR_PERSONAL,
    DIR_SKILLS,
    DIR_PROTOCOLS,
    DIR_TOOLS,
    DIR_DATA_LAYER,
    DIR_FLYWHEEL,
]


# ── PREFERENCES.md parser ──────────────────────────────────────────────

# PREFERENCES.md uses a simple key: value format
_PREF_RE = re.compile(r"^\s*[-*]\s+\*\*(.+?)\*\*:\s*(.+)$", re.MULTILINE)


def _parse_preferences_md(text: str) -> Dict[str, str]:
    """Parse PREFERENCES.md into a dict of preference key -> value."""
    prefs: Dict[str, str] = {}
    for m in _PREF_RE.finditer(text):
        key = m.group(1).strip().lower().replace(" ", "_")
        value = m.group(2).strip()
        prefs[key] = value
    return prefs


def _render_preferences_md(prefs: Dict[str, str]) -> str:
    """Render a preferences dict into PREFERENCES.md format."""
    lines = ["# Personal Preferences", ""]
    labels = {
        "preferred_name": "Preferred Name",
        "primary_language": "Primary Language",
        "explanation_style": "Explanation Style",
        "testing_strategy": "Testing Strategy",
        "commit_message_style": "Commit Message Style",
        "code_review_depth": "Code Review Depth",
    }
    for key, value in prefs.items():
        label = labels.get(key, key.replace("_", " ").title())
        lines.append(f"- **{label}**: {value}")
    lines.append("")
    return "\n".join(lines)


# ── permissions.md parser ──────────────────────────────────────────────

def _parse_permissions_md(text: str) -> List[dict]:
    """Parse permissions.md into a list of constraint dicts for AgentConfig."""
    constraints: List[dict] = []
    # Simple: each bullet or numbered item under a "##" heading becomes a constraint
    current_section = ""
    for line in text.splitlines():
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            current_section = heading.group(1).strip().lower()
            continue
        bullet = re.match(r"^\s*[-*]\s+(.+)$", line)
        if bullet and current_section:
            desc = bullet.group(1).strip()
            constraint_type = "forbidden_keyword"
            if "block" in current_section or "forbidden" in current_section:
                constraint_type = "forbidden_keyword"
            elif "confirm" in current_section or "approval" in current_section:
                constraint_type = "requires_confirmation"
            constraints.append({
                "id": f"perm-{len(constraints)}",
                "type": constraint_type,
                "description": desc,
                "keywords": desc.split()[:5],
                "action": "block" if "block" in current_section else "confirm",
            })
    return constraints


def _render_permissions_md(constraints: List[dict]) -> str:
    """Render AgentConfig constraints into permissions.md format."""
    blocked = [c for c in constraints if c.get("action") == "block"]
    confirmed = [c for c in constraints if c.get("action") in ("confirm", "confirm_on")]

    lines = ["# Permissions", ""]
    if blocked:
        lines.append("## Blocked Actions")
        lines.append("")
        for c in blocked:
            lines.append(f"- {c.get('description', '')}")
        lines.append("")
    if confirmed:
        lines.append("## Requires Confirmation")
        lines.append("")
        for c in confirmed:
            lines.append(f"- {c.get('description', '')}")
        lines.append("")
    if not blocked and not confirmed:
        lines.append("No permission constraints defined.")
        lines.append("")
    return "\n".join(lines)


# ── JSONL helpers ───────────────────────────────────────────────────────

def _read_jsonl(path: Path) -> List[dict]:
    """Read a JSONL file, returning a list of dicts. Returns [] if missing."""
    if not path.exists():
        return []
    items: List[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return items


def _append_jsonl(path: Path, item: dict) -> None:
    """Append a single JSON object as a line to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _write_jsonl(path: Path, items: List[dict]) -> None:
    """Write a list of dicts to a JSONL file (overwrite)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


# ── Core: AgentDir class ───────────────────────────────────────────────

class AgentDir:
    """
    Object-oriented interface to a .agent/ portable directory.

    Provides methods to load/save AgentConfig, read/write skills,
    lessons, preferences, and permissions within the standard layout.

    Example::

        agent_dir = AgentDir(".agent/")
        config = agent_dir.load_config()
        skills = agent_dir.list_skills()
        prefs = agent_dir.load_preferences()
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        # If the path name is already ".agent", use it directly
        if self.path.name == AGENT_DIR_NAME:
            pass
        else:
            # If user passes a project root, check if .agent/ exists inside it
            candidate = self.path / AGENT_DIR_NAME
            if candidate.exists():
                self.path = candidate

    # ── Config ──────────────────────────────────────────────────────

    def load_config(self) -> AgentConfig:
        """
        Load AgentConfig from the .agent/config.yaml file.

        Falls back to config.json if YAML is not available.

        Returns:
            AgentConfig instance.

        Raises:
            FileNotFoundError: If no config file exists in the directory.
        """
        # Try config.yaml first
        yaml_path = self.path / "config.yaml"
        if yaml_path.exists():
            return self._load_yaml_config(yaml_path)

        # Fallback to config.json
        json_path = self.path / "config.json"
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return AgentConfig.from_dict(data)

        raise FileNotFoundError(
            f"No config.yaml or config.json found in {self.path}"
        )

    def save_config(self, config: AgentConfig) -> None:
        """
        Save AgentConfig to .agent/config.yaml.

        Also writes companion files: AGENTS.md, permissions.md,
        and PREFERENCES.md from the config data.

        Args:
            config: AgentConfig instance to save.
        """
        self.path.mkdir(parents=True, exist_ok=True)

        # Write config.yaml
        self._save_yaml_config(config)

        # Write AGENTS.md overview
        self._write_agents_md(config)

        # Write permissions.md from constraints
        if config.constraints:
            perm_path = self.path / FILE_PERMISSIONS_MD
            perm_path.parent.mkdir(parents=True, exist_ok=True)
            perm_path.write_text(
                _render_permissions_md(config.constraints), encoding="utf-8"
            )

        # Write PREFERENCES.md from metadata
        prefs = config.metadata.get("preferences")
        if prefs and isinstance(prefs, dict):
            pref_path = self.path / FILE_PREFERENCES_MD
            pref_path.parent.mkdir(parents=True, exist_ok=True)
            pref_path.write_text(
                _render_preferences_md(prefs), encoding="utf-8"
            )

    def _load_yaml_config(self, yaml_path: Path) -> AgentConfig:
        """Load AgentConfig from a YAML file."""
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "YAML support requires 'pyyaml'. Install with: pip install pyyaml"
            )
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config.yaml must contain a mapping")
        return AgentConfig.from_dict(data)

    def _save_yaml_config(self, config: AgentConfig) -> None:
        """Save AgentConfig as config.yaml."""
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "YAML support requires 'pyyaml'. Install with: pip install pyyaml"
            )
        config_path = self.path / CONFIG_FILENAME
        config_path.write_text(
            yaml.dump(
                config.to_dict(),
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def _write_agents_md(self, config: AgentConfig) -> None:
        """Write AGENTS.md navigation file."""
        lines = [
            f"# {config.name}",
            "",
            f"**Version**: {config.version}",
            f"**Description**: {config.description or 'No description'}",
            f"**Created**: {config.created_at}",
            "",
            "## Directory Map",
            "",
            "| Path | Purpose |",
            "|------|---------|",
            "| `config.yaml` | AgentConfig main configuration |",
            "| `memory/working/` | Working (short-term) memory |",
            "| `memory/episodic/` | Episodic (historical) memory |",
            "| `memory/semantic/` | Semantic memory (lessons) |",
            "| `memory/personal/` | Personal preferences |",
            "| `skills/` | Skill definitions |",
            "| `protocols/` | Permissions and hook patterns |",
        ]
        if config.mcp_servers:
            lines.append("| `config.yaml → mcp_servers` | MCP server declarations |")
        lines.append("")
        (self.path / FILE_AGENTS_MD).write_text(
            "\n".join(lines), encoding="utf-8"
        )

    # ── Skills ──────────────────────────────────────────────────────

    def list_skills(self) -> List[dict]:
        """Read the skill manifest (_manifest.jsonl). Returns list of skill dicts."""
        return _read_jsonl(self.path / FILE_SKILL_MANIFEST)

    def add_skill(self, name: str, description: str = "", triggers: Optional[List[str]] = None) -> None:
        """
        Add a skill entry to the manifest.

        Args:
            name: Skill name (used as directory name under skills/).
            description: Short description of the skill.
            triggers: List of trigger patterns for the skill.
        """
        manifest_path = self.path / FILE_SKILL_MANIFEST
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "name": name,
            "description": description,
            "triggers": triggers or [],
            "added_at": datetime.now(timezone.utc).isoformat(),
        }
        _append_jsonl(manifest_path, entry)

        # Create skill directory with placeholder SKILL.md
        skill_dir = self.path / DIR_SKILLS / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            skill_md.write_text(
                f"# {name}\n\n{description}\n", encoding="utf-8"
            )

    # ── Lessons ─────────────────────────────────────────────────────

    def list_lessons(self) -> List[dict]:
        """Read graduated lessons from lessons.jsonl. Returns list of lesson dicts."""
        return _read_jsonl(self.path / FILE_LESSONS_JSONL)

    def add_lesson(self, lesson: str, category: str = "general", rationale: str = "") -> None:
        """
        Add a graduated lesson to lessons.jsonl.

        Args:
            lesson: The lesson text.
            category: Category tag for the lesson.
            rationale: Why this lesson was accepted.
        """
        entry = {
            "lesson": lesson,
            "category": category,
            "rationale": rationale,
            "graduated_at": datetime.now(timezone.utc).isoformat(),
        }
        lessons_path = self.path / FILE_LESSONS_JSONL
        _append_jsonl(lessons_path, entry)

        # Re-render LESSONS.md
        self._render_lessons_md()

    def _render_lessons_md(self) -> None:
        """Re-render LESSONS.md from lessons.jsonl."""
        lessons = self.list_lessons()
        lines = ["# Lessons", ""]
        for i, l in enumerate(lessons, 1):
            lines.append(f"## {i}. {l.get('category', 'general').title()}")
            lines.append("")
            lines.append(l.get("lesson", ""))
            if l.get("rationale"):
                lines.append(f"\n*Rationale: {l['rationale']}*")
            lines.append("")
        (self.path / FILE_LESSONS_MD).write_text(
            "\n".join(lines), encoding="utf-8"
        )

    # ── Preferences ─────────────────────────────────────────────────

    def load_preferences(self) -> Dict[str, str]:
        """Load personal preferences from PREFERENCES.md."""
        pref_path = self.path / FILE_PREFERENCES_MD
        if not pref_path.exists():
            return {}
        return _parse_preferences_md(pref_path.read_text(encoding="utf-8"))

    def save_preferences(self, prefs: Dict[str, str]) -> None:
        """Save personal preferences to PREFERENCES.md."""
        pref_path = self.path / FILE_PREFERENCES_MD
        pref_path.parent.mkdir(parents=True, exist_ok=True)
        pref_path.write_text(_render_preferences_md(prefs), encoding="utf-8")

    # ── Permissions ─────────────────────────────────────────────────

    def load_permissions(self) -> List[dict]:
        """Load permission constraints from permissions.md."""
        perm_path = self.path / FILE_PERMISSIONS_MD
        if not perm_path.exists():
            return []
        return _parse_permissions_md(perm_path.read_text(encoding="utf-8"))

    # ── Init ────────────────────────────────────────────────────────

    def init(
        self,
        config: Optional[AgentConfig] = None,
        with_defaults: bool = True,
    ) -> None:
        """
        Initialize a .agent/ directory with the standard layout.

        Creates all subdirectories and optional default files.
        If a config is provided, saves it as config.yaml.

        Args:
            config: Optional AgentConfig to save as config.yaml.
            with_defaults: If True, creates default PREFERENCES.md and AGENTS.md.
        """
        # Create all subdirectories
        for subdir in ALL_SUBDIRS:
            (self.path / subdir).mkdir(parents=True, exist_ok=True)

        # Create .gitkeep in empty dirs that need it
        for subdir in [DIR_WORKING, DIR_EPISODIC, DIR_TOOLS, DIR_DATA_LAYER, DIR_FLYWHEEL]:
            gitkeep = self.path / subdir / ".gitkeep"
            gitkeep.touch(exist_ok=True)

        # Save config
        if config:
            self.save_config(config)
        elif with_defaults:
            # Create minimal config.yaml
            default_config = AgentConfig(name="My Agent")
            self._save_yaml_config(default_config)
            self._write_agents_md(default_config)

        # Default PREFERENCES.md
        if with_defaults:
            pref_path = self.path / FILE_PREFERENCES_MD
            if not pref_path.exists():
                default_prefs = {
                    "primary_language": "unspecified",
                    "explanation_style": "concise",
                    "testing_strategy": "test-after",
                    "commit_message_style": "conventional commits",
                    "code_review_depth": "critical issues only",
                }
                pref_path.write_text(
                    _render_preferences_md(default_prefs), encoding="utf-8"
                )

        # Default permissions.md
        if with_defaults:
            perm_path = self.path / FILE_PERMISSIONS_MD
            if not perm_path.exists():
                perm_path.write_text(
                    "# Permissions\n\nNo permission constraints defined.\n",
                    encoding="utf-8",
                )

        # Default empty skill manifest
        manifest_path = self.path / FILE_SKILL_MANIFEST
        if not manifest_path.exists():
            manifest_path.write_text("", encoding="utf-8")

        # Default skill index
        index_path = self.path / FILE_SKILL_INDEX
        if not index_path.exists():
            index_path.write_text("# Skills Index\n\nNo skills registered.\n", encoding="utf-8")


# ── Public convenience functions ────────────────────────────────────────

def load_agent_dir(path: str | Path) -> AgentConfig:
    """
    Load an AgentConfig from a .agent/ portable directory.

    This is the main entry point for reading agentic-stack compatible
    .agent/ directories.

    Args:
        path: Path to the .agent/ directory (or its parent).

    Returns:
        AgentConfig instance loaded from config.yaml (or config.json).

    Raises:
        FileNotFoundError: If the directory or config file doesn't exist.

    Example::

        from agentconfig.portable import load_agent_dir

        config = load_agent_dir(".agent/")
        print(config.name)
    """
    return AgentDir(path).load_config()


def save_agent_dir(config: AgentConfig, path: str | Path) -> None:
    """
    Save an AgentConfig to a .agent/ portable directory.

    Writes config.yaml, AGENTS.md, and any companion files derived
    from the config (permissions, preferences).

    If *path* does not end in ``.agent/``, the directory ``.agent/`` will
    be created inside it automatically.

    Args:
        config: AgentConfig instance to save.
        path: Path to the .agent/ directory (or its parent).

    Example::

        from agentconfig.portable import save_agent_dir
        from agentconfig.semantic.config_gen import AgentConfig

        config = AgentConfig(name="ResearchAgent")
        save_agent_dir(config, ".agent/")
    """
    p = Path(path)
    # If path is not already .agent/, create .agent/ inside it
    if p.name != AGENT_DIR_NAME:
        p = p / AGENT_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    AgentDir(p).save_config(config)


def init_agent_dir(
    path: str | Path,
    config: Optional[AgentConfig] = None,
    with_defaults: bool = True,
) -> AgentDir:
    """
    Initialize a .agent/ directory with the standard layout.

    Args:
        path: Path to the .agent/ directory (or its parent).
        config: Optional AgentConfig to save as config.yaml.
        with_defaults: If True, creates default files.

    Returns:
        AgentDir instance for the initialized directory.

    Example::

        from agentconfig.portable import init_agent_dir

        agent_dir = init_agent_dir(".agent/")
        agent_dir.add_skill("research", "Deep research capability")
    """
    p = Path(path)
    if p.name != AGENT_DIR_NAME:
        p = p / AGENT_DIR_NAME
    d = AgentDir(p)
    d.init(config=config, with_defaults=with_defaults)
    return d
