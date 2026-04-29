"""
Tests for config validation (Issue #1) and multi-format loader (Issue #2).
"""

import pytest
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agentconfig.validation import validate_config, validate_dict, ValidationResult, ValidationError
from agentconfig.loader import load_config, save_config, list_formats
from agentconfig.semantic.config_gen import AgentConfig, ModelConfig, ConfigGenerator
from agentconfig.semantic.intent import IntentParser


# ── Validation Tests (Issue #1) ──────────────────────────────────────────

class TestValidationResult:

    def test_valid_result_is_truthy(self):
        r = ValidationResult(valid=True)
        assert bool(r) is True

    def test_invalid_result_is_falsy(self):
        r = ValidationResult(valid=False, errors=[ValidationError(path="x", message="bad")])
        assert bool(r) is False

    def test_str_valid(self):
        r = ValidationResult(valid=True)
        assert "passed" in str(r).lower()

    def test_str_invalid(self):
        r = ValidationResult(valid=False, errors=[ValidationError(path="name", message="missing")])
        assert "failed" in str(r).lower()
        assert "name" in str(r)


class TestValidateDict:

    def test_valid_minimal_config(self):
        result = validate_dict({"name": "Test Agent"})
        assert result.valid, f"Unexpected errors: {result.errors}"

    def test_valid_full_config(self):
        config = {
            "name": "Full Agent",
            "version": "1.0.0",
            "description": "A fully configured agent",
            "system_prompt": "You are helpful.",
            "max_turns": 25,
            "stream": True,
            "log_enabled": False,
            "audit_enabled": True,
            "model": {
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "temperature": 0.5,
                "max_tokens": 2048,
            },
            "intent": {
                "name": "Full Agent",
                "domain": "customer_service",
                "tone": ["friendly", "concise"],
            },
            "tools_enabled": ["web_search"],
            "tools_disabled": ["file_write"],
            "metadata": {"env": "test"},
        }
        result = validate_dict(config)
        assert result.valid, f"Unexpected errors: {result.errors}"

    def test_missing_required_name(self):
        result = validate_dict({"description": "no name"})
        assert not result.valid
        assert any("name" in e.path for e in result.errors)

    def test_invalid_domain(self):
        result = validate_dict({
            "name": "Agent",
            "intent": {"name": "Agent", "domain": "invalid_domain"},
        })
        assert not result.valid

    def test_invalid_tone(self):
        result = validate_dict({
            "name": "Agent",
            "intent": {"name": "Agent", "tone": ["sarcastic"]},
        })
        assert not result.valid

    def test_invalid_provider(self):
        result = validate_dict({
            "name": "Agent",
            "model": {"provider": "nonexistent_provider"},
        })
        assert not result.valid

    def test_temperature_out_of_range(self):
        result = validate_dict({
            "name": "Agent",
            "model": {"temperature": 5.0},
        })
        assert not result.valid

    def test_max_turns_out_of_range(self):
        result = validate_dict({
            "name": "Agent",
            "max_turns": 0,
        })
        assert not result.valid

    def test_invalid_constraint_type(self):
        result = validate_dict({
            "name": "Agent",
            "constraints": [{"id": "c1", "type": "bad_type", "description": "test"}],
        })
        assert not result.valid

    def test_valid_constraint(self):
        result = validate_dict({
            "name": "Agent",
            "constraints": [{
                "id": "no-pricing",
                "type": "forbidden_keyword",
                "description": "No pricing info",
                "keywords": ["price"],
                "action": "block",
            }],
        })
        assert result.valid, f"Unexpected errors: {result.errors}"

    def test_unknown_field_rejected(self):
        result = validate_dict({
            "name": "Agent",
            "nonexistent_field": "should fail",
        })
        assert not result.valid
        assert any("nonexistent_field" in e.path or "Unknown" in e.message for e in result.errors)

    def test_empty_dict_fails(self):
        result = validate_dict({})
        assert not result.valid


class TestValidateConfigFile:

    def test_valid_json_file(self, tmp_path):
        config = {"name": "File Agent", "version": "1.0.0"}
        path = str(tmp_path / "agent.json")
        with open(path, "w") as f:
            json.dump(config, f)
        result = validate_config(path)
        assert result.valid, f"Unexpected errors: {result.errors}"

    def test_invalid_json_file(self, tmp_path):
        config = {"description": "missing name"}
        path = str(tmp_path / "bad.json")
        with open(path, "w") as f:
            json.dump(config, f)
        result = validate_config(path)
        assert not result.valid

    def test_nonexistent_file(self):
        result = validate_config("/nonexistent/path/agent.json")
        assert not result.valid

    def test_unsupported_format(self, tmp_path):
        path = str(tmp_path / "agent.xml")
        with open(path, "w") as f:
            f.write("<agent/>")
        result = validate_config(path)
        assert not result.valid
        assert any("Unsupported" in e.message for e in result.errors)

    def test_malformed_json(self, tmp_path):
        path = str(tmp_path / "broken.json")
        with open(path, "w") as f:
            f.write("{invalid json!!!")
        result = validate_config(path)
        assert not result.valid
        assert any("Parse error" in e.message for e in result.errors)


# ── Loader Tests (Issue #2) ──────────────────────────────────────────────

class TestLoadConfig:

    def test_load_json(self, tmp_path):
        config = AgentConfig(name="JSON Agent", version="1.0.0")
        path = str(tmp_path / "agent.json")
        config.save(path)
        loaded = load_config(path)
        assert loaded.name == "JSON Agent"
        assert loaded.version == "1.0.0"

    def test_load_yaml(self, tmp_path):
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")

        yaml_content = """
name: YAML Agent
version: "2.0.0"
description: Loaded from YAML
max_turns: 30
model:
  provider: anthropic
  model: claude-3-5-sonnet-20241022
  temperature: 0.5
"""
        path = str(tmp_path / "agent.yaml")
        with open(path, "w") as f:
            f.write(yaml_content)
        loaded = load_config(path)
        assert loaded.name == "YAML Agent"
        assert loaded.model.provider == "anthropic"
        assert loaded.max_turns == 30

    def test_load_toml(self, tmp_path):
        try:
            import tomllib
        except ImportError:
            try:
                import tomli
            except ImportError:
                pytest.skip("TOML support not available")

        toml_content = '''
name = "TOML Agent"
version = "1.0.0"
description = "Loaded from TOML"
max_turns = 25
stream = true

[model]
provider = "ollama"
model = "llama3"
temperature = 0.8
'''
        path = str(tmp_path / "agent.toml")
        with open(path, "w") as f:
            f.write(toml_content)
        loaded = load_config(path)
        assert loaded.name == "TOML Agent"
        assert loaded.model.provider == "ollama"
        assert loaded.stream is True

    def test_load_nonexistent_file(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/agent.json")

    def test_load_unsupported_format(self, tmp_path):
        path = str(tmp_path / "agent.xml")
        with open(path, "w") as f:
            f.write("<agent/>")
        with pytest.raises(ValueError, match="Cannot detect format"):
            load_config(path)


class TestSaveConfig:

    def test_save_json(self, tmp_path):
        config = AgentConfig(name="Save Test")
        path = str(tmp_path / "saved.json")
        save_config(config, path)
        loaded = load_config(path)
        assert loaded.name == "Save Test"

    def test_save_yaml(self, tmp_path):
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")

        config = AgentConfig(name="YAML Save Test", version="1.0.0")
        path = str(tmp_path / "saved.yaml")
        save_config(config, path)
        loaded = load_config(path)
        assert loaded.name == "YAML Save Test"

    def test_save_and_load_roundtrip_json(self, tmp_path):
        parser = IntentParser()
        gen = ConfigGenerator()
        intent = parser.parse("Handle complaints politely. Never mention pricing.", name="Roundtrip")
        original = gen.generate(intent)
        path = str(tmp_path / "roundtrip.json")
        save_config(original, path)
        loaded = load_config(path)
        assert loaded.name == original.name
        assert loaded.config_id == original.config_id

    def test_save_and_load_roundtrip_yaml(self, tmp_path):
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")

        parser = IntentParser()
        gen = ConfigGenerator()
        intent = parser.parse("Sales agent for B2B.", name="YAML Roundtrip")
        original = gen.generate(intent)
        path = str(tmp_path / "roundtrip.yaml")
        save_config(original, path)
        loaded = load_config(path)
        assert loaded.name == original.name


class TestListFormats:

    def test_returns_supported_formats(self):
        formats = list_formats()
        assert "json" in formats
        assert "yaml" in formats
        assert "toml" in formats

    def test_returns_sorted_list(self):
        formats = list_formats()
        assert formats == sorted(formats)


# ── Integration: Validate loaded configs ──────────────────────────────────

class TestValidateLoadedConfigs:

    def test_validated_generated_config(self):
        """Generated configs should always validate."""
        parser = IntentParser()
        gen = ConfigGenerator()
        intent = parser.parse("Handle support politely.", name="Validation Test")
        config = gen.generate(intent)
        result = validate_dict(config.to_dict())
        assert result.valid, f"Generated config failed validation: {result.errors}"

    def test_validate_yaml_example(self):
        """The YAML example file should validate."""
        example_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "examples", "customer_support.yaml"
        )
        if not os.path.exists(example_path):
            pytest.skip("YAML example not found")
        result = validate_config(example_path)
        assert result.valid, f"YAML example failed validation: {result.errors}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
