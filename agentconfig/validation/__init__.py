"""
Config Validation — JSON Schema-based validation for AgentConfig.

Provides IDE autocomplete support and runtime validation for agent
configuration files. Supports JSON, YAML, and TOML formats.

Usage::

    from agentconfig.validation import validate_config, ValidationResult

    result = validate_config("my_agent.json")
    if not result.valid:
        for err in result.errors:
            print(f"  {err.path}: {err.message}")
"""

from agentconfig.validation.validator import validate_config, validate_dict, ValidationResult, ValidationError

__all__ = ["validate_config", "validate_dict", "ValidationResult", "ValidationError"]
