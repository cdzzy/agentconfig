"""
Tests for agentconfig.portable — .agent/ portable directory support.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from agentconfig.portable import (
    AgentDir,
    load_agent_dir,
    save_agent_dir,
    init_agent_dir,
    _parse_preferences_md,
    _render_preferences_md,
    _parse_permissions_md,
    _render_permissions_md,
    _read_jsonl,
    _write_jsonl,
    _append_jsonl,
)
from agentconfig.semantic.config_gen import AgentConfig, ModelConfig


# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory."""
    return tmp_path


@pytest.fixture
def sample_config():
    """Provide a sample AgentConfig."""
    config = AgentConfig(
        name="TestAgent",
        version="2.0.0",
        description="A test agent for portable directory tests",
        system_prompt="You are a helpful test agent.",
        model=ModelConfig(provider="anthropic", model="claude-3"),
        constraints=[
            {
                "id": "c1",
                "type": "forbidden_keyword",
                "description": "Never reveal API keys",
                "keywords": ["api_key", "secret"],
                "action": "block",
            },
            {
                "id": "c2",
                "type": "requires_confirmation",
                "description": "Confirm before deleting files",
                "keywords": ["delete", "remove"],
                "action": "confirm",
            },
        ],
        tools_enabled=["search", "read"],
        tools_disabled=["write"],
        mcp_servers=[
            {"name": "web-search", "command": "npx", "args": ["-y", "@anthropic/mcp-server-brave"]},
        ],
        metadata={
            "preferences": {
                "primary_language": "Chinese",
                "explanation_style": "detailed",
                "testing_strategy": "test-first",
            },
        },
    )
    return config


# ── Preferences parsing ─────────────────────────────────────────────────

class TestPreferencesMd:
    def test_parse_preferences(self):
        text = """# Personal Preferences

- **Preferred Name**: Alex
- **Primary Language**: Chinese
- **Explanation Style**: concise
- **Testing Strategy**: test-first
"""
        prefs = _parse_preferences_md(text)
        assert prefs["preferred_name"] == "Alex"
        assert prefs["primary_language"] == "Chinese"
        assert prefs["explanation_style"] == "concise"
        assert prefs["testing_strategy"] == "test-first"

    def test_parse_empty_preferences(self):
        prefs = _parse_preferences_md("")
        assert prefs == {}

    def test_render_preferences_roundtrip(self):
        prefs = {
            "primary_language": "Chinese",
            "explanation_style": "concise",
        }
        rendered = _render_preferences_md(prefs)
        parsed = _parse_preferences_md(rendered)
        assert parsed["primary_language"] == "Chinese"
        assert parsed["explanation_style"] == "concise"


# ── Permissions parsing ─────────────────────────────────────────────────

class TestPermissionsMd:
    def test_parse_permissions(self):
        text = """# Permissions

## Blocked Actions

- Never reveal API keys
- Never access user passwords

## Requires Confirmation

- Confirm before deleting files
"""
        constraints = _parse_permissions_md(text)
        assert len(constraints) == 3
        # First two are blocked
        assert constraints[0]["action"] == "block"
        assert constraints[1]["action"] == "block"
        # Third requires confirmation
        assert constraints[2]["action"] == "confirm"

    def test_parse_empty_permissions(self):
        constraints = _parse_permissions_md("")
        assert constraints == []

    def test_render_permissions(self):
        constraints = [
            {"description": "Never reveal API keys", "action": "block"},
            {"description": "Confirm before deleting", "action": "confirm"},
        ]
        rendered = _render_permissions_md(constraints)
        assert "## Blocked Actions" in rendered
        assert "## Requires Confirmation" in rendered
        assert "Never reveal API keys" in rendered


# ── JSONL helpers ───────────────────────────────────────────────────────

class TestJsonl:
    def test_read_write_jsonl(self, tmp_dir):
        path = tmp_dir / "test.jsonl"
        items = [{"name": "a", "value": 1}, {"name": "b", "value": 2}]
        _write_jsonl(path, items)
        result = _read_jsonl(path)
        assert len(result) == 2
        assert result[0]["name"] == "a"
        assert result[1]["value"] == 2

    def test_read_missing_jsonl(self, tmp_dir):
        result = _read_jsonl(tmp_dir / "nonexistent.jsonl")
        assert result == []

    def test_append_jsonl(self, tmp_dir):
        path = tmp_dir / "append.jsonl"
        _write_jsonl(path, [{"name": "first"}])
        _append_jsonl(path, {"name": "second"})
        result = _read_jsonl(path)
        assert len(result) == 2
        assert result[1]["name"] == "second"


# ── AgentDir ────────────────────────────────────────────────────────────

class TestAgentDir:
    def test_init_creates_directory_structure(self, tmp_dir):
        agent_dir = AgentDir(tmp_dir / ".agent")
        agent_dir.init()
        assert (tmp_dir / ".agent" / "config.yaml").exists()
        assert (tmp_dir / ".agent" / "AGENTS.md").exists()
        assert (tmp_dir / ".agent" / "memory" / "working").exists()
        assert (tmp_dir / ".agent" / "memory" / "episodic").exists()
        assert (tmp_dir / ".agent" / "memory" / "semantic").exists()
        assert (tmp_dir / ".agent" / "memory" / "personal").exists()
        assert (tmp_dir / ".agent" / "skills").exists()
        assert (tmp_dir / ".agent" / "protocols").exists()
        assert (tmp_dir / ".agent" / "skills" / "_manifest.jsonl").exists()
        assert (tmp_dir / ".agent" / "memory" / "personal" / "PREFERENCES.md").exists()

    def test_init_with_config(self, tmp_dir, sample_config):
        agent_dir = AgentDir(tmp_dir / ".agent")
        agent_dir.init(config=sample_config)
        config = agent_dir.load_config()
        assert config.name == "TestAgent"
        assert config.version == "2.0.0"

    def test_save_and_load_config(self, tmp_dir, sample_config):
        agent_dir = AgentDir(tmp_dir / ".agent")
        agent_dir.save_config(sample_config)
        loaded = agent_dir.load_config()
        assert loaded.name == sample_config.name
        assert loaded.version == sample_config.version
        assert loaded.description == sample_config.description
        assert loaded.system_prompt == sample_config.system_prompt
        assert loaded.model.provider == "anthropic"
        assert loaded.model.model == "claude-3"
        assert len(loaded.constraints) == 2
        assert len(loaded.mcp_servers) == 1

    def test_save_creates_companion_files(self, tmp_dir, sample_config):
        agent_dir = AgentDir(tmp_dir / ".agent")
        agent_dir.save_config(sample_config)
        # AGENTS.md
        agents_md = (tmp_dir / ".agent" / "AGENTS.md").read_text(encoding="utf-8")
        assert "TestAgent" in agents_md
        # permissions.md
        perm_md = (tmp_dir / ".agent" / "protocols" / "permissions.md").read_text(encoding="utf-8")
        assert "Never reveal API keys" in perm_md
        # PREFERENCES.md
        pref_md = (tmp_dir / ".agent" / "memory" / "personal" / "PREFERENCES.md").read_text(encoding="utf-8")
        assert "Chinese" in pref_md

    def test_skills_add_and_list(self, tmp_dir):
        agent_dir = AgentDir(tmp_dir / ".agent")
        agent_dir.init()
        agent_dir.add_skill("research", "Deep research capability", ["research", "investigate"])
        agent_dir.add_skill("debug", "Debug investigation", ["debug", "fix"])
        skills = agent_dir.list_skills()
        assert len(skills) == 2
        assert skills[0]["name"] == "research"
        assert skills[1]["name"] == "debug"
        # SKILL.md created
        assert (tmp_dir / ".agent" / "skills" / "research" / "SKILL.md").exists()
        assert (tmp_dir / ".agent" / "skills" / "debug" / "SKILL.md").exists()

    def test_lessons_add_and_list(self, tmp_dir):
        agent_dir = AgentDir(tmp_dir / ".agent")
        agent_dir.init()
        agent_dir.add_lesson("Always validate inputs", category="security", rationale="Prevent injection")
        agent_dir.add_lesson("Use descriptive names", category="coding")
        lessons = agent_dir.list_lessons()
        assert len(lessons) == 2
        assert lessons[0]["lesson"] == "Always validate inputs"
        assert lessons[0]["category"] == "security"
        # LESSONS.md rendered
        lessons_md = (tmp_dir / ".agent" / "memory" / "semantic" / "LESSONS.md").read_text(encoding="utf-8")
        assert "Always validate inputs" in lessons_md

    def test_preferences_save_and_load(self, tmp_dir):
        agent_dir = AgentDir(tmp_dir / ".agent")
        agent_dir.init()
        prefs = {"primary_language": "Japanese", "explanation_style": "verbose"}
        agent_dir.save_preferences(prefs)
        loaded = agent_dir.load_preferences()
        assert loaded["primary_language"] == "Japanese"
        assert loaded["explanation_style"] == "verbose"

    def test_load_config_fallback_to_json(self, tmp_dir, sample_config):
        agent_dir = AgentDir(tmp_dir / ".agent")
        agent_dir.path.mkdir(parents=True, exist_ok=True)
        # Write config.json directly (no config.yaml)
        json_path = agent_dir.path / "config.json"
        json_path.write_text(sample_config.to_json(), encoding="utf-8")
        loaded = agent_dir.load_config()
        assert loaded.name == "TestAgent"

    def test_load_config_file_not_found(self, tmp_dir):
        agent_dir = AgentDir(tmp_dir / ".agent_empty")
        with pytest.raises(FileNotFoundError, match="No config.yaml or config.json"):
            agent_dir.load_config()

    def test_agent_dir_auto_detects_dot_agent(self, tmp_dir):
        """If passed a parent dir containing .agent/, should resolve to it."""
        dot_agent = tmp_dir / ".agent"
        dot_agent.mkdir()
        (dot_agent / "config.yaml").write_text(
            "name: AutoDetect\nversion: '1.0'\n", encoding="utf-8"
        )
        agent_dir = AgentDir(tmp_dir)
        assert agent_dir.path == dot_agent


# ── Convenience functions ───────────────────────────────────────────────

class TestConvenienceFunctions:
    def test_load_agent_dir(self, tmp_dir, sample_config):
        save_agent_dir(sample_config, tmp_dir)
        loaded = load_agent_dir(tmp_dir)
        assert loaded.name == sample_config.name

    def test_save_agent_dir(self, tmp_dir, sample_config):
        save_agent_dir(sample_config, tmp_dir)
        assert (tmp_dir / ".agent" / "config.yaml").exists()

    def test_init_agent_dir(self, tmp_dir):
        agent_dir = init_agent_dir(tmp_dir, with_defaults=True)
        assert (agent_dir.path / "config.yaml").exists()
        assert (agent_dir.path / "AGENTS.md").exists()
