"""
Tests for agentconfig.gateway — SKILL.md / AGENTS.md bidirectional markdown
gateway (importer, exporter, round-trips, validation, CLI subcommands).
"""

import json
from pathlib import Path

import pytest

from agentconfig.gateway import (
    AGENTS,
    SKILL,
    ConfigTree,
    GatewayParseError,
    GatewayValidationError,
    parse_agents_md,
    parse_skill_md,
    render_agents_md,
    render_skill_md,
    validate_skill_tree,
)
from agentconfig.cli.main import cli


# ── Fixtures ────────────────────────────────────────────────────────────

SAMPLE_SKILL_MD = """---
name: pdf-report
description: Generate polished PDF reports from structured data.
license: MIT
allowed-tools: Read, Write, Bash
version: 1.2.0
---

# PDF Report

Use this skill to turn structured records into a polished PDF report.

## Steps

1. Collect the source records.
2. Render each section with the report template.
"""

SAMPLE_AGENTS_MD = """# AGENTS.md

Instructions for coding agents working in this repository.

## Build commands

- `pytest -q` — run the test suite
- `ruff check .` — lint

## Code style

Use type hints everywhere. Never commit secrets.
"""


@pytest.fixture
def skill_file(tmp_path) -> Path:
    path = tmp_path / "SKILL.md"
    path.write_text(SAMPLE_SKILL_MD, encoding="utf-8")
    return path


@pytest.fixture
def agents_file(tmp_path) -> Path:
    path = tmp_path / "AGENTS.md"
    path.write_text(SAMPLE_AGENTS_MD, encoding="utf-8")
    return path


@pytest.fixture
def skill_tree() -> ConfigTree:
    return parse_skill_md(SAMPLE_SKILL_MD)


@pytest.fixture
def agents_tree() -> ConfigTree:
    return parse_agents_md(SAMPLE_AGENTS_MD)


# ── SKILL.md importer ───────────────────────────────────────────────────


class TestParseSkillMd:
    def test_parses_frontmatter_fields(self, skill_tree):
        assert skill_tree.kind == SKILL
        assert skill_tree.name == "pdf-report"
        assert skill_tree.description == "Generate polished PDF reports from structured data."
        assert skill_tree.license == "MIT"
        assert skill_tree.allowed_tools == ["Read", "Write", "Bash"]
        assert skill_tree.has_frontmatter is True

    def test_body_preserved_after_frontmatter(self, skill_tree):
        assert skill_tree.body.startswith("# PDF Report")
        assert "2. Render each section" in skill_tree.body

    def test_unknown_frontmatter_keys_kept_in_extras(self, skill_tree):
        assert skill_tree.extras == {"version": "1.2.0"}

    def test_allowed_tools_as_list(self):
        md = "---\nname: a\ndescription: d\nallowed-tools:\n  - Read\n  - Grep\n---\n\nbody\n"
        tree = parse_skill_md(md)
        assert tree.allowed_tools == ["Read", "Grep"]

    def test_missing_frontmatter_raises_clear_error(self):
        with pytest.raises(GatewayParseError) as excinfo:
            parse_skill_md("# Just markdown\n\nno frontmatter here\n")
        message = str(excinfo.value)
        assert "missing YAML frontmatter" in message
        assert "'name'" in message and "'description'" in message

    def test_invalid_yaml_raises_clear_error(self):
        with pytest.raises(GatewayParseError) as excinfo:
            parse_skill_md("---\nname: [unclosed\n---\n\nbody\n")
        assert "invalid YAML in frontmatter" in str(excinfo.value)

    def test_non_mapping_frontmatter_raises_clear_error(self):
        with pytest.raises(GatewayParseError) as excinfo:
            parse_skill_md("---\n- a\n- b\n---\n\nbody\n")
        assert "frontmatter must be a YAML mapping" in str(excinfo.value)

    def test_missing_name_raises(self):
        with pytest.raises(GatewayParseError) as excinfo:
            parse_skill_md("---\ndescription: d\n---\n\nbody\n")
        assert "'name' is missing or empty" in str(excinfo.value)

    def test_missing_description_raises(self):
        with pytest.raises(GatewayParseError) as excinfo:
            parse_skill_md("---\nname: my-skill\n---\n\nbody\n")
        assert "'description' is missing or empty" in str(excinfo.value)

    def test_source_name_included_in_error(self):
        with pytest.raises(GatewayParseError) as excinfo:
            parse_skill_md("no frontmatter", source="skills/other/SKILL.md")
        assert "skills/other/SKILL.md" in str(excinfo.value)

    def test_non_string_name_raises(self):
        with pytest.raises(GatewayParseError) as excinfo:
            parse_skill_md("---\nname: [1, 2]\ndescription: d\n---\n\nbody\n")
        assert "field 'name' must be a string" in str(excinfo.value)


# ── AGENTS.md importer ──────────────────────────────────────────────────


class TestParseAgentsMd:
    def test_plain_agents_md_without_frontmatter(self, agents_tree):
        assert agents_tree.kind == AGENTS
        assert agents_tree.name == "AGENTS.md"  # derived from the H1
        assert agents_tree.has_frontmatter is False
        assert agents_tree.license is None

    def test_sections_extracted_as_project_config(self, agents_tree):
        assert "build_commands" in agents_tree.sections
        assert "code_style" in agents_tree.sections
        assert "`pytest -q`" in agents_tree.sections["build_commands"]
        assert "Never commit secrets." in agents_tree.sections["code_style"]

    def test_name_falls_back_to_file_stem(self, tmp_path):
        text = "Just some instructions, no heading."
        tree = parse_agents_md(text, source="MyProject.md")
        assert tree.name == "MyProject"

    def test_description_falls_back_to_first_prose_paragraph(self):
        text = "# Title\n\n- a list item\n\nReal prose paragraph here.\n"
        tree = parse_agents_md(text)
        assert tree.description == "Real prose paragraph here."

    def test_frontmatter_accepted(self):
        text = (
            "---\nname: my-project\ndescription: Project instructions\n"
            "license: Apache-2.0\nallowed-tools: Read, Edit\n---\n\n# Project\n\nbody\n"
        )
        tree = parse_agents_md(text)
        assert tree.has_frontmatter is True
        assert tree.name == "my-project"
        assert tree.description == "Project instructions"
        assert tree.license == "Apache-2.0"
        assert tree.allowed_tools == ["Read", "Edit"]

    def test_empty_file_raises_clear_error(self):
        with pytest.raises(GatewayParseError) as excinfo:
            parse_agents_md("   \n\n  ", source="AGENTS.md")
        assert "file is empty" in str(excinfo.value)

    def test_invalid_frontmatter_yaml_raises(self):
        with pytest.raises(GatewayParseError) as excinfo:
            parse_agents_md("---\nkey: : bad\n---\n\nbody\n")
        assert "invalid YAML" in str(excinfo.value)


# ── Validation (export-side required-field checks) ──────────────────────


class TestValidateSkillTree:
    def test_valid_tree_has_no_errors(self, skill_tree):
        assert validate_skill_tree(skill_tree) == []

    def test_missing_name_reported(self):
        errors = validate_skill_tree(ConfigTree(kind=SKILL, description="d"))
        assert any("'name' is required" in e for e in errors)

    def test_missing_description_reported(self):
        errors = validate_skill_tree(ConfigTree(kind=SKILL, name="ok-name"))
        assert any("'description' is required" in e for e in errors)

    def test_invalid_name_format_reported(self):
        errors = validate_skill_tree(ConfigTree(kind=SKILL, name="My Skill!", description="d"))
        assert any("invalid skill name" in e for e in errors)

    def test_oversized_description_reported(self):
        errors = validate_skill_tree(
            ConfigTree(kind=SKILL, name="ok-name", description="x" * 2000)
        )
        assert any("limit is 1024" in e for e in errors)


# ── SKILL.md exporter ───────────────────────────────────────────────────


class TestRenderSkillMd:
    def test_renders_required_frontmatter_first(self, skill_tree):
        md = render_skill_md(skill_tree)
        assert md.startswith("---\nname: pdf-report\ndescription:")
        assert "license: MIT" in md
        assert "allowed-tools: Read, Write, Bash" in md
        assert md.rstrip().endswith("2. Render each section with the report template.")

    def test_strict_render_rejects_missing_description(self):
        tree = ConfigTree(kind=SKILL, name="ok-name", description="")
        with pytest.raises(GatewayValidationError) as excinfo:
            render_skill_md(tree)
        assert "frontmatter validation failed" in str(excinfo.value)
        assert "'description' is required" in str(excinfo.value)

    def test_non_strict_render_allows_incomplete_tree(self):
        tree = ConfigTree(kind=SKILL, name="ok-name", description="")
        md = render_skill_md(tree, strict=False)
        assert md.startswith("---\nname: ok-name")

    def test_extras_round_trip_into_frontmatter(self, skill_tree):
        md = render_skill_md(skill_tree)
        assert "version: 1.2.0" in md


# ── AGENTS.md exporter ──────────────────────────────────────────────────


class TestRenderAgentsMd:
    def test_plain_agents_md_round_trips_textually(self, agents_tree):
        assert render_agents_md(agents_tree) == SAMPLE_AGENTS_MD

    def test_frontmatter_agents_md_keeps_frontmatter(self):
        text = (
            "---\nname: my-project\ndescription: Instructions\n---\n\n# Project\n\nbody\n"
        )
        tree = parse_agents_md(text)
        rendered = render_agents_md(tree)
        assert rendered.startswith("---\n")
        assert "name: my-project" in rendered
        assert parse_agents_md(rendered) == tree


# ── Round-trip (lossless) ───────────────────────────────────────────────


class TestRoundTrip:
    def test_skill_round_trip_tree_lossless(self, skill_tree):
        rendered = render_skill_md(skill_tree)
        assert parse_skill_md(rendered) == skill_tree

    def test_skill_round_trip_is_idempotent(self, skill_tree):
        once = render_skill_md(skill_tree)
        twice = render_skill_md(parse_skill_md(once))
        assert once == twice

    def test_skill_round_trip_with_list_allowed_tools(self):
        md = (
            "---\nname: web-scraper\ndescription: Scrape and summarize pages.\n"
            "allowed-tools:\n  - WebFetch\n  - Bash(python:*)\nmodel: sonnet\n---\n\n"
            "# Web Scraper\n\nBody with `code` and **bold**.\n"
        )
        tree = parse_skill_md(md)
        assert parse_skill_md(render_skill_md(tree)) == tree

    def test_agents_round_trip_tree_lossless(self, agents_tree):
        rendered = render_agents_md(agents_tree)
        assert parse_agents_md(rendered) == agents_tree

    def test_agents_round_trip_is_idempotent(self, agents_tree):
        once = render_agents_md(agents_tree)
        twice = render_agents_md(parse_agents_md(once))
        assert once == twice

    def test_skill_to_agents_cross_export(self, skill_tree):
        """A skill tree can be exported as AGENTS.md (project-level view)."""
        rendered = render_agents_md(skill_tree)
        tree = parse_agents_md(rendered)
        assert tree.name == "pdf-report"
        assert tree.allowed_tools == skill_tree.allowed_tools


# ── Config tree serialization ───────────────────────────────────────────


class TestConfigTree:
    def test_to_dict_from_dict_round_trip(self, skill_tree):
        data = json.loads(json.dumps(skill_tree.to_dict()))
        assert ConfigTree.from_dict(data) == skill_tree

    def test_from_dict_rejects_unknown_kind(self):
        with pytest.raises(GatewayValidationError) as excinfo:
            ConfigTree.from_dict({"kind": "wat", "name": "x"})
        assert "unknown config tree kind" in str(excinfo.value)

    def test_from_dict_rejects_non_object(self):
        with pytest.raises(GatewayValidationError) as excinfo:
            ConfigTree.from_dict([1, 2, 3])
        assert "must be a JSON object" in str(excinfo.value)

    def test_from_dict_rejects_bad_allowed_tools(self):
        with pytest.raises(GatewayValidationError) as excinfo:
            ConfigTree.from_dict({"kind": "skill", "allowed_tools": "Read"})
        assert "allowed_tools" in str(excinfo.value)

    def test_to_agent_config_dict_consumed_by_agentconfig_core(self, skill_tree):
        from agentconfig.semantic.config_gen import AgentConfig

        config = AgentConfig.from_dict(skill_tree.to_agent_config_dict())
        assert config.name == "pdf-report"
        assert config.description == skill_tree.description
        assert config.tools_enabled == ["Read", "Write", "Bash"]
        assert "PDF Report" in config.system_prompt
        assert config.metadata["source"] == "gateway:skill"


# ── CLI: agentconfig skill import / export ──────────────────────────────


class TestCliSkill:
    def test_import_prints_tree_json(self, skill_file, capsys):
        rc = cli(["skill", "import", "--source", str(skill_file)])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["kind"] == "skill"
        assert payload["name"] == "pdf-report"
        assert payload["license"] == "MIT"

    def test_import_writes_output_file(self, skill_file, tmp_path, capsys):
        out = tmp_path / "out" / "tree.json"
        rc = cli(["skill", "import", "--source", str(skill_file), "--output", str(out)])
        assert rc == 0
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["name"] == "pdf-report"

    def test_import_agents_md_by_filename(self, agents_file, capsys):
        rc = cli(["skill", "import", "--source", str(agents_file)])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["kind"] == "agents"
        assert "build_commands" in payload["sections"]

    def test_import_missing_file_fails(self, capsys):
        rc = cli(["skill", "import", "--source", "does-not-exist.md"])
        assert rc == 1
        assert "file not found" in capsys.readouterr().err

    def test_import_malformed_file_fails_with_clear_error(self, tmp_path, capsys):
        bad = tmp_path / "SKILL.md"
        bad.write_text("# no frontmatter\n", encoding="utf-8")
        rc = cli(["skill", "import", "--source", str(bad)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "missing YAML frontmatter" in err

    def test_export_renders_skill_md(self, skill_tree, tmp_path, capsys):
        tree_file = tmp_path / "tree.json"
        tree_file.write_text(json.dumps(skill_tree.to_dict()), encoding="utf-8")
        out = tmp_path / "SKILL.md"
        rc = cli(["skill", "export", "--config", str(tree_file), "--target", "skill",
                  "--output", str(out)])
        assert rc == 0
        content = out.read_text(encoding="utf-8")
        assert content.startswith("---\nname: pdf-report\n")

    def test_export_renders_agents_md(self, agents_tree, tmp_path, capsys):
        tree_file = tmp_path / "tree.json"
        tree_file.write_text(json.dumps(agents_tree.to_dict()), encoding="utf-8")
        out = tmp_path / "AGENTS.md"
        rc = cli(["skill", "export", "--config", str(tree_file), "--target", "agents",
                  "--output", str(out)])
        assert rc == 0
        assert out.read_text(encoding="utf-8") == SAMPLE_AGENTS_MD

    def test_export_to_stdout(self, skill_tree, tmp_path, capsys):
        tree_file = tmp_path / "tree.json"
        tree_file.write_text(json.dumps(skill_tree.to_dict()), encoding="utf-8")
        rc = cli(["skill", "export", "--config", str(tree_file), "--target", "skill"])
        assert rc == 0
        out = capsys.readouterr().out
        assert out.startswith("---\nname: pdf-report\n")

    def test_export_fails_validation_with_clear_error(self, tmp_path, capsys):
        tree_file = tmp_path / "bad.json"
        tree_file.write_text(json.dumps({"kind": "skill", "name": "x", "description": ""}),
                             encoding="utf-8")
        rc = cli(["skill", "export", "--config", str(tree_file), "--target", "skill"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "frontmatter validation failed" in err
        assert "'description' is required" in err

    def test_export_invalid_json_fails(self, tmp_path, capsys):
        tree_file = tmp_path / "broken.json"
        tree_file.write_text("{not json", encoding="utf-8")
        rc = cli(["skill", "export", "--config", str(tree_file), "--target", "skill"])
        assert rc == 1
        assert "invalid JSON" in capsys.readouterr().err

    def test_export_unknown_kind_fails(self, tmp_path, capsys):
        tree_file = tmp_path / "tree.json"
        tree_file.write_text(json.dumps({"kind": "mystery"}), encoding="utf-8")
        rc = cli(["skill", "export", "--config", str(tree_file), "--target", "skill"])
        assert rc == 1
        assert "unknown config tree kind" in capsys.readouterr().err

    def test_export_missing_config_file_fails(self, capsys):
        rc = cli(["skill", "export", "--config", "nope.json", "--target", "skill"])
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_full_round_trip_through_cli(self, skill_file, tmp_path):
        tree_file = tmp_path / "tree.json"
        exported = tmp_path / "SKILL.md"
        assert cli(["skill", "import", "--source", str(skill_file), "--output", str(tree_file)]) == 0
        assert cli(["skill", "export", "--config", str(tree_file), "--target", "skill",
                    "--output", str(exported)]) == 0
        # Re-import the exported file: must yield the identical tree.
        re_tree_file = tmp_path / "tree2.json"
        assert cli(["skill", "import", "--source", str(exported), "--output", str(re_tree_file)]) == 0
        assert json.loads(re_tree_file.read_text(encoding="utf-8")) == \
            json.loads(tree_file.read_text(encoding="utf-8"))
