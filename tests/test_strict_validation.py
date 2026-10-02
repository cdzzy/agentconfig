"""
Tests for the optional Pydantic v2 strict validation mode.

Covers:
- Strictness enum + normalize_mode coercion
- validate_dict_strict happy paths (minimal / full configs, int-or-float numbers)
- strict-mode rejections the lenient walker cannot catch (silent type
  coercion, multiple simultaneous violations, Literal enum drift)
- validate_dict / validate_config mode dispatch
- graceful fallback when pydantic is not installed
- ValidationResult extensions (mode / notes / model)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from agentconfig.validation import (
    Strictness,
    ValidationError,
    ValidationResult,
    normalize_mode,
    pydantic_available,
    validate_config,
    validate_dict,
    validate_dict_strict,
)

_HAS_PYDANTIC = pydantic_available()
requires_pydantic = pytest.mark.skipif(
    not _HAS_PYDANTIC, reason="pydantic v2 is not installed"
)

# ── Fixtures ──────────────────────────────────────────────────────────────

VALID_MINIMAL = {"name": "Test Agent"}

VALID_FULL = {
    "name": "Support Agent",
    "version": "1.2.0",
    "description": "A customer support agent.",
    "intent": {
        "name": "resolve_tickets",
        "purpose": "Resolve inbound support tickets",
        "domain": "customer_service",
        "tone": ["professional", "empathetic"],
        "max_turns": 12,
        "goals": ["close ticket"],
    },
    "model": {
        "provider": "openai",
        "model": "gpt-4o",
        "temperature": 0.3,
        "max_tokens": 4096,
        "top_p": 1,
        "timeout_seconds": 30,
    },
    "constraints": [
        {
            "id": "no_pii",
            "type": "forbidden_keyword",
            "description": "Never expose raw PII",
            "action": "block",
            "keywords": ["ssn", "credit_card"],
        }
    ],
    "tools_enabled": ["search"],
    "tools_disabled": ["shell"],
    "max_turns": 20,
    "stream": True,
    "log_enabled": False,
    "audit_enabled": True,
    "metadata": {"team": "support", "tier": 2},
    "mcp_servers": [
        {
            "name": "filesystem",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"],
            "env": {"FS_ROOT": "/data"},
        }
    ],
    "tool_policy": {
        "allowed_tools": ["fs_read"],
        "blocked_tools": ["fs_write"],
        "auto_approve": False,
        "require_confirmation": ["fs_write"],
    },
}


# ── Strictness enum ───────────────────────────────────────────────────────

class TestStrictnessEnum:
    def test_member_values(self):
        assert Strictness.LENIENT.value == "lenient"
        assert Strictness.STRICT.value == "strict"

    def test_is_string_subclass(self):
        # Strictness inherits str, so it drops into f-strings / JSON / CLI
        # arguments without explicit conversion.
        assert isinstance(Strictness.STRICT, str)
        assert Strictness.STRICT == "strict"
        assert f"mode={Strictness.LENIENT}" == "mode=lenient"

    def test_lookup_by_value(self):
        assert Strictness("strict") is Strictness.STRICT


class TestNormalizeMode:
    def test_none_defaults_to_lenient(self):
        assert normalize_mode(None) is Strictness.LENIENT

    def test_string_modes(self):
        assert normalize_mode("lenient") is Strictness.LENIENT
        assert normalize_mode("strict") is Strictness.STRICT

    def test_string_case_insensitive(self):
        assert normalize_mode("STRICT") is Strictness.STRICT
        assert normalize_mode("Lenient") is Strictness.LENIENT

    def test_enum_passthrough(self):
        assert normalize_mode(Strictness.STRICT) is Strictness.STRICT
        assert normalize_mode(Strictness.LENIENT) is Strictness.LENIENT

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown validation mode"):
            normalize_mode("bogus")

    def test_error_message_lists_valid_modes(self):
        with pytest.raises(ValueError, match="lenient.*strict"):
            normalize_mode(123)


# ── validate_dict_strict: happy paths ─────────────────────────────────────

@requires_pydantic
class TestValidateDictStrictValid:
    def test_minimal_config(self):
        result = validate_dict_strict(VALID_MINIMAL)
        assert result.valid is True
        assert result.mode == "strict"
        assert result.errors == []
        assert result.model is not None
        assert result.model.name == "Test Agent"

    def test_full_config(self):
        result = validate_dict_strict(VALID_FULL)
        assert result.valid is True
        assert result.mode == "strict"
        assert result.model.max_turns == 20
        assert result.model.intent.domain == "customer_service"
        assert result.model.model.temperature == 0.3
        assert result.model.tool_policy.auto_approve is False

    def test_integer_temperature_accepted(self):
        # JSON Schema "number" accepts ints; strict mode must not reject
        # temperature: 1 just because it parsed as an int.
        result = validate_dict_strict(
            {"name": "X", "model": {"temperature": 1}}
        )
        assert result.valid is True
        assert result.model.model.temperature == 1

    def test_integer_top_p_accepted(self):
        result = validate_dict_strict({"name": "X", "model": {"top_p": 0}})
        assert result.valid is True
        assert result.model.model.top_p == 0

    def test_roundtrip_dict(self):
        result = validate_dict_strict(VALID_FULL)
        dumped = result.model.model_dump()
        assert dumped["name"] == "Support Agent"
        assert dumped["intent"]["tone"] == ["professional", "empathetic"]

    def test_bool_passes_through(self):
        result = validate_dict_strict({"name": "X", "stream": True})
        assert result.valid is True
        assert result.model.stream is True


# ── validate_dict_strict: rejections ──────────────────────────────────────

@requires_pydantic
class TestValidateDictStrictInvalid:
    def test_missing_name(self):
        result = validate_dict_strict({"version": "1.0.0"})
        assert result.valid is False
        assert result.mode == "strict"
        assert any("name" in err.path for err in result.errors)

    def test_string_max_turns_rejected(self):
        # Strict mode performs no silent coercion: "20" must NOT become 20.
        result = validate_dict_strict({"name": "X", "max_turns": "20"})
        assert result.valid is False
        assert any("max_turns" in err.path for err in result.errors)

    def test_bool_max_turns_rejected(self):
        result = validate_dict_strict({"name": "X", "max_turns": True})
        assert result.valid is False

    def test_multiple_violations_reported_at_once(self):
        # The built-in walker stops at the first type mismatch in a
        # subtree; strict mode reports every violation in one pass.
        result = validate_dict_strict(
            {"name": "X", "max_turns": "20", "model": {"temperature": 9}}
        )
        assert result.valid is False
        paths = [err.path for err in result.errors]
        assert "max_turns" in paths
        assert "model.temperature" in paths
        assert len(result.errors) >= 2

    def test_unknown_top_level_field_rejected(self):
        result = validate_dict_strict({"name": "X", "totally_new_field": 1})
        assert result.valid is False
        assert any("totally_new_field" in err.path for err in result.errors)

    def test_unknown_nested_field_rejected(self):
        cfg = {"name": "X", "intent": {"name": "i", "unknown": True}}
        result = validate_dict_strict(cfg)
        assert result.valid is False
        assert any("intent.unknown" in err.path for err in result.errors)

    def test_invalid_domain_literal(self):
        cfg = {"name": "X", "intent": {"name": "i", "domain": "rocket_science"}}
        result = validate_dict_strict(cfg)
        assert result.valid is False
        assert any("intent.domain" in err.path for err in result.errors)

    def test_invalid_tone_literal(self):
        cfg = {"name": "X", "intent": {"name": "i", "tone": ["sarcastic"]}}
        result = validate_dict_strict(cfg)
        assert result.valid is False

    def test_invalid_provider_literal(self):
        result = validate_dict_strict(
            {"name": "X", "model": {"provider": " blockbuster"}}
        )
        assert result.valid is False

    def test_temperature_out_of_range(self):
        result = validate_dict_strict(
            {"name": "X", "model": {"temperature": 2.5}}
        )
        assert result.valid is False
        assert any("temperature" in err.path for err in result.errors)

    def test_bad_version_pattern(self):
        result = validate_dict_strict({"name": "X", "version": "v1.2"})
        assert result.valid is False
        assert any("version" in err.path for err in result.errors)

    def test_invalid_constraint_type(self):
        cfg = {
            "name": "X",
            "constraints": [
                {"id": "c1", "type": "telepathy_check", "description": "no"}
            ],
        }
        result = validate_dict_strict(cfg)
        assert result.valid is False
        assert any("constraints.0.type" in err.path for err in result.errors)

    def test_errors_are_validation_error_instances(self):
        result = validate_dict_strict({"name": 123})
        assert result.valid is False
        assert all(isinstance(err, ValidationError) for err in result.errors)

    def test_string_name_rejected(self):
        result = validate_dict_strict({"name": 123})
        assert result.valid is False
        assert result.model is None

    def test_str_result_lists_all_errors(self):
        result = validate_dict_strict(
            {"name": "X", "max_turns": "20", "stream": "yes"}
        )
        rendered = str(result)
        assert "Validation failed" in rendered
        assert "max_turns" in rendered
        assert "stream" in rendered


# ── Mode dispatch through validate_dict / validate_config ─────────────────

class TestValidateDictModeDispatch:
    def test_default_is_lenient(self):
        result = validate_dict(VALID_MINIMAL)
        assert result.valid is True
        assert result.mode == "lenient"
        assert result.model is None

    def test_invalid_dict_still_lenient_by_default(self):
        result = validate_dict({"max_turns": "20"})  # missing name + bad type
        assert result.valid is False
        assert result.mode == "lenient"

    @requires_pydantic
    def test_string_mode_dispatches_to_strict(self):
        result = validate_dict(VALID_MINIMAL, mode="strict")
        assert result.valid is True
        assert result.mode == "strict"
        assert result.model is not None

    @requires_pydantic
    def test_enum_mode_dispatches_to_strict(self):
        result = validate_dict(VALID_MINIMAL, mode=Strictness.STRICT)
        assert result.valid is True
        assert result.mode == "strict"
        assert result.model.name == "Test Agent"

    @requires_pydantic
    def test_lenient_enum_stays_lenient(self):
        result = validate_dict(VALID_MINIMAL, mode=Strictness.LENIENT)
        assert result.valid is True
        assert result.mode == "lenient"
        assert result.model is None

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="Unknown validation mode"):
            validate_dict(VALID_MINIMAL, mode="turbo")

    @requires_pydantic
    def test_strict_and_direct_call_agree(self):
        via_dispatch = validate_dict(VALID_FULL, mode="strict")
        direct = validate_dict_strict(VALID_FULL)
        assert via_dispatch.valid == direct.valid is True
        assert via_dispatch.model.name == direct.model.name


class TestValidateConfigModeDispatch:
    def test_missing_file_lenient_by_default(self, tmp_path):
        result = validate_config(str(tmp_path / "nope.json"))
        assert result.valid is False
        assert result.mode == "lenient"

    @requires_pydantic
    def test_json_file_strict_mode(self, tmp_path):
        import json

        cfg_file = tmp_path / "agent.json"
        cfg_file.write_text(json.dumps(VALID_MINIMAL), encoding="utf-8")
        result = validate_config(str(cfg_file), mode="strict")
        assert result.valid is True
        assert result.mode == "strict"
        assert result.model.name == "Test Agent"

    @requires_pydantic
    def test_yaml_file_strict_mode(self, tmp_path):
        import yaml

        cfg_file = tmp_path / "agent.yaml"
        cfg_file.write_text(yaml.safe_dump(VALID_FULL), encoding="utf-8")
        result = validate_config(str(cfg_file), mode=Strictness.STRICT)
        assert result.valid is True
        assert result.mode == "strict"
        assert result.model.intent.name == "resolve_tickets"

    @requires_pydantic
    def test_yaml_file_strict_rejects_bad_types(self, tmp_path):
        # YAML 1.1 parsers can silently coerce values; strict mode then
        # catches what slipped through the load step.
        import yaml

        bad = {"name": "X", "stream": "yes"}
        cfg_file = tmp_path / "agent.yaml"
        cfg_file.write_text(yaml.safe_dump(bad), encoding="utf-8")
        result = validate_config(str(cfg_file), mode="strict")
        assert result.valid is False
        assert result.mode == "strict"
        assert any("stream" in err.path for err in result.errors)


# ── Fallback when pydantic is missing ─────────────────────────────────────

class TestFallbackBehavior:
    def test_fallback_uses_builtin_and_notes(self, monkeypatch):
        import agentconfig.validation.strict as strict_mod

        monkeypatch.setattr(strict_mod, "_HAS_PYDANTIC", False)
        result = strict_mod.validate_dict_strict(VALID_MINIMAL)
        assert result.valid is True
        assert result.mode == "lenient"
        assert len(result.notes) == 1
        assert "pydantic" in result.notes[0]
        assert "cdzzy-agentconfig[strict]" in result.notes[0]
        assert result.model is None

    def test_fallback_still_catches_schema_errors(self, monkeypatch):
        import agentconfig.validation.strict as strict_mod

        monkeypatch.setattr(strict_mod, "_HAS_PYDANTIC", False)
        result = strict_mod.validate_dict_strict({"max_turns": 5})
        assert result.valid is False  # missing required "name"
        assert result.mode == "lenient"

    def test_fallback_shows_note_in_str(self, monkeypatch):
        import agentconfig.validation.strict as strict_mod

        monkeypatch.setattr(strict_mod, "_HAS_PYDANTIC", False)
        result = strict_mod.validate_dict_strict(VALID_MINIMAL)
        assert "Notes" in str(result)

    def test_pydantic_available_returns_bool(self):
        assert isinstance(pydantic_available(), bool)


# ── ValidationResult extensions ───────────────────────────────────────────

class TestValidationResultExtensions:
    def test_defaults_backwards_compatible(self):
        # Old call sites construct ValidationResult(valid=..., errors=...)
        # without mode/notes/model — they must keep working untouched.
        result = ValidationResult(valid=True, errors=[])
        assert result.mode == "lenient"
        assert result.notes == []
        assert result.model is None

    def test_str_without_notes_unchanged(self):
        ok = ValidationResult(valid=True)
        assert str(ok) == "Validation passed ✓"
        bad = ValidationResult(
            valid=False,
            errors=[ValidationError(path="name", message="missing")],
        )
        assert "Validation failed" in str(bad)
        assert "name" in str(bad)

    def test_str_with_notes_appends_block(self):
        result = ValidationResult(valid=True, notes=["heads up"])
        rendered = str(result)
        assert "Validation passed" in rendered
        assert "Notes" in rendered
        assert "heads up" in rendered

    def test_truthiness_preserved(self):
        assert bool(ValidationResult(valid=True)) is True
        assert bool(ValidationResult(valid=False)) is False
