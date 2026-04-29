"""
JSON Schema-based validation for AgentConfig.

Validates configuration files and dicts against the official schema,
providing clear error messages for invalid configs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any


# ── Schema path ──────────────────────────────────────────────────────────

_SCHEMA_DIR = Path(__file__).resolve().parent.parent.parent / "schemas"
_AGENT_CONFIG_SCHEMA = _SCHEMA_DIR / "agent-config.schema.json"


def _load_schema() -> dict:
    """Load the AgentConfig JSON Schema."""
    with open(_AGENT_CONFIG_SCHEMA, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Data structures ──────────────────────────────────────────────────────

@dataclass
class ValidationError:
    """A single validation error."""
    path: str
    message: str
    value: Optional[Any] = None

    def __str__(self) -> str:
        prefix = f"[{self.path}] " if self.path else ""
        return f"{prefix}{self.message}"


@dataclass
class ValidationResult:
    """Result of validating an AgentConfig."""
    valid: bool = True
    errors: List[ValidationError] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.valid

    def __str__(self) -> str:
        if self.valid:
            return "Validation passed ✓"
        lines = [f"Validation failed ({len(self.errors)} error(s)):"]
        for err in self.errors:
            lines.append(f"  • {err}")
        return "\n".join(lines)


# ── Built-in validation (no external dependency) ────────────────────────

def _validate_dict_builtin(data: dict, schema: dict, path: str = "", root_schema: Optional[dict] = None) -> List[ValidationError]:
    """
    Validate a dict against a JSON Schema using built-in logic.

    Supports: type, required, properties, additionalProperties, enum,
    minimum, maximum, minLength, maxLength, minItems, pattern, items, $ref.
    """
    errors: List[ValidationError] = []

    # Resolve $ref
    if "$ref" in schema and root_schema:
        ref_path = schema["$ref"]
        if ref_path.startswith("#/definitions/"):
            def_name = ref_path.split("/")[-1]
            resolved = root_schema.get("definitions", {}).get(def_name, schema)
            # Merge original schema (minus $ref) with resolved
            merged = {k: v for k, v in schema.items() if k != "$ref"}
            merged.update(resolved)
            schema = merged

    # Type check
    if "type" in schema:
        expected_type = schema["type"]
        if isinstance(expected_type, list):
            # Union type like ["string", "null"]
            type_ok = any(_check_type(data, t) for t in expected_type)
        else:
            type_ok = _check_type(data, expected_type)
        if not type_ok:
            errors.append(ValidationError(
                path=path,
                message=f"Expected type {expected_type}, got {type(data).__name__}",
                value=data,
            ))
            return errors  # Stop further checks on type mismatch

    # oneOf check
    if "oneOf" in schema:
        one_of_schemas = schema["oneOf"]
        match_count = 0
        for sub_schema in one_of_schemas:
            sub_errors = _validate_dict_builtin(data, sub_schema, path, root_schema)
            if not sub_errors:
                match_count += 1
        if match_count != 1:
            errors.append(ValidationError(
                path=path,
                message=f"Value must match exactly one schema in oneOf, matched {match_count}",
                value=data,
            ))
            return errors

    # Enum check
    if "enum" in schema and data not in schema["enum"]:
        errors.append(ValidationError(
            path=path,
            message=f"Value must be one of {schema['enum']}, got {data!r}",
            value=data,
        ))

    # Pattern check (strings)
    if "pattern" in schema and isinstance(data, str):
        import re
        if not re.match(schema["pattern"], data):
            errors.append(ValidationError(
                path=path,
                message=f"String does not match pattern {schema['pattern']!r}",
                value=data,
            ))

    # String length checks
    if isinstance(data, str):
        if "minLength" in schema and len(data) < schema["minLength"]:
            errors.append(ValidationError(
                path=path,
                message=f"String too short: {len(data)} < {schema['minLength']}",
                value=data,
            ))
        if "maxLength" in schema and len(data) > schema["maxLength"]:
            errors.append(ValidationError(
                path=path,
                message=f"String too long: {len(data)} > {schema['maxLength']}",
                value=data,
            ))

    # Number range checks
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        if "minimum" in schema and data < schema["minimum"]:
            errors.append(ValidationError(
                path=path,
                message=f"Value too small: {data} < {schema['minimum']}",
                value=data,
            ))
        if "maximum" in schema and data > schema["maximum"]:
            errors.append(ValidationError(
                path=path,
                message=f"Value too large: {data} > {schema['maximum']}",
                value=data,
            ))

    # Array checks
    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            errors.append(ValidationError(
                path=path,
                message=f"Array too short: {len(data)} < {schema['minItems']}",
                value=data,
            ))
        if "items" in schema:
            item_schema = schema["items"]
            # Resolve $ref in items if needed
            if "$ref" in item_schema and root_schema:
                ref_path = item_schema["$ref"]
                if ref_path.startswith("#/definitions/"):
                    def_name = ref_path.split("/")[-1]
                    item_schema = root_schema.get("definitions", {}).get(def_name, item_schema)
            for i, item in enumerate(data):
                item_path = f"{path}[{i}]" if path else f"[{i}]"
                errors.extend(_validate_dict_builtin(item, item_schema, item_path, root_schema))

    # Object checks
    if isinstance(data, dict):
        # Required fields
        if "required" in schema:
            for req in schema["required"]:
                if req not in data:
                    errors.append(ValidationError(
                        path=f"{path}.{req}" if path else req,
                        message=f"Required field missing",
                    ))

        # Properties
        if "properties" in schema:
            for key, prop_schema in schema["properties"].items():
                if key in data:
                    prop_path = f"{path}.{key}" if path else key
                    # Resolve $ref in property schema
                    resolved_prop = prop_schema
                    if "$ref" in prop_schema and root_schema:
                        ref_path = prop_schema["$ref"]
                        if ref_path.startswith("#/definitions/"):
                            def_name = ref_path.split("/")[-1]
                            resolved_prop = root_schema.get("definitions", {}).get(def_name, prop_schema)
                    errors.extend(_validate_dict_builtin(data[key], resolved_prop, prop_path, root_schema))
                # Also validate if key not in data but schema has oneOf and data might have it from parent
                # (This handles the case where tool_policy can be null)

        # additionalProperties
        if "additionalProperties" in schema and schema["additionalProperties"] is False:
            allowed = set(schema.get("properties", {}).keys())
            for key in data:
                if key not in allowed:
                    errors.append(ValidationError(
                        path=f"{path}.{key}" if path else key,
                        message=f"Unknown field (not in schema)",
                        value=key,
                    ))

    return errors


def _check_type(value: Any, expected: str) -> bool:
    """Check if a value matches a JSON Schema type string."""
    if expected == "string":
        return isinstance(value, str)
    elif expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    elif expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected == "boolean":
        return isinstance(value, bool)
    elif expected == "array":
        return isinstance(value, list)
    elif expected == "object":
        return isinstance(value, dict)
    elif expected == "null":
        return value is None
    return True


# ── Schema-aware $ref resolver ───────────────────────────────────────────

def _resolve_ref(schema: dict, root_schema: dict) -> dict:
    """Resolve $ref in a schema using the root schema's definitions."""
    if "$ref" not in schema:
        return schema
    ref = schema["$ref"]
    if ref.startswith("#/definitions/"):
        def_name = ref.split("/")[-1]
        return root_schema.get("definitions", {}).get(def_name, schema)
    return schema


def _validate_with_refs(data: Any, schema: dict, root_schema: dict, path: str = "") -> List[ValidationError]:
    """Validate with automatic $ref resolution."""
    return _validate_dict_builtin(data, schema, path, root_schema)


# ── Public API ───────────────────────────────────────────────────────────

def validate_dict(data: dict) -> ValidationResult:
    """
    Validate a dict representing an AgentConfig against the JSON Schema.

    Args:
        data: Dict to validate (as from json.load / yaml.safe_load).

    Returns:
        ValidationResult with valid=True/False and list of errors.

    Example::

        from agentconfig.validation import validate_dict

        result = validate_dict({"name": "My Agent", "max_turns": 20})
        if not result.valid:
            print(result)
    """
    try:
        schema = _load_schema()
    except FileNotFoundError:
        return ValidationResult(
            valid=False,
            errors=[ValidationError(
                path="",
                message="Schema file not found. Ensure schemas/agent-config.schema.json exists.",
            )],
        )

    errors = _validate_with_refs(data, schema, schema)

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
    )


def validate_config(path: str) -> ValidationResult:
    """
    Validate an agent config file (JSON, YAML, or TOML) against the schema.

    Args:
        path: Path to the configuration file. Format is detected by extension:
              - .json → JSON
              - .yaml / .yml → YAML (requires pyyaml)
              - .toml → TOML (requires tomli for Python < 3.11)

    Returns:
        ValidationResult with valid=True/False and list of errors.

    Example::

        from agentconfig.validation import validate_config

        result = validate_config("my_agent.yaml")
        print(result)
    """
    filepath = Path(path)
    if not filepath.exists():
        return ValidationResult(
            valid=False,
            errors=[ValidationError(path="", message=f"File not found: {path}")],
        )

    ext = filepath.suffix.lower()

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw = f.read()
    except Exception as e:
        return ValidationResult(
            valid=False,
            errors=[ValidationError(path="", message=f"Failed to read file: {e}")],
        )

    # Parse based on extension
    try:
        if ext == ".json":
            data = json.loads(raw)
        elif ext in (".yaml", ".yml"):
            try:
                import yaml
            except ImportError:
                return ValidationResult(
                    valid=False,
                    errors=[ValidationError(
                        path="",
                        message="YAML support requires 'pyyaml' package. Install with: pip install pyyaml",
                    )],
                )
            data = yaml.safe_load(raw)
        elif ext == ".toml":
            try:
                import tomllib  # Python 3.11+
            except ImportError:
                try:
                    import tomli as tomllib  # Python < 3.11
                except ImportError:
                    return ValidationResult(
                        valid=False,
                        errors=[ValidationError(
                            path="",
                            message="TOML support requires Python 3.11+ or 'tomli' package. Install with: pip install tomli",
                        )],
                    )
            import io
            data = tomllib.loads(raw)
        else:
            return ValidationResult(
                valid=False,
                errors=[ValidationError(
                    path="",
                    message=f"Unsupported file format: {ext}. Use .json, .yaml, or .toml",
                )],
            )
    except Exception as e:
        return ValidationResult(
            valid=False,
            errors=[ValidationError(path="", message=f"Parse error: {e}")],
        )

    if not isinstance(data, dict):
        return ValidationResult(
            valid=False,
            errors=[ValidationError(path="", message=f"Config must be a mapping, got {type(data).__name__}")],
        )

    return validate_dict(data)
