"""
Config Validation — JSON Schema-based validation for AgentConfig.

Provides IDE autocomplete support and runtime validation for agent
configuration files. Supports JSON, YAML, and TOML formats.

Two validation modes are available:

- ``lenient`` (default) — built-in, zero-dependency JSON Schema walker.
- ``strict`` — optional pydantic v2 models (``pip install
  "cdzzy-agentconfig[strict]"``) that reject silent type coercion,
  report every violation at once, and expose a typed ``result.model``.

Usage::

    from agentconfig.validation import validate_config, Strictness

    result = validate_config("my_agent.json", mode=Strictness.STRICT)
    if not result.valid:
        for err in result.errors:
            print(f"  {err.path}: {err.message}")
"""

from agentconfig.validation.strict import (
    Strictness,
    normalize_mode,
    pydantic_available,
    validate_dict_strict,
)
from agentconfig.validation.validator import (
    ValidationError,
    ValidationResult,
    get_schema,
    schema_file,
    validate_config,
    validate_dict,
)

__all__ = [
    "validate_config",
    "validate_dict",
    "validate_dict_strict",
    "get_schema",
    "schema_file",
    "ValidationResult",
    "ValidationError",
    "Strictness",
    "normalize_mode",
    "pydantic_available",
]
