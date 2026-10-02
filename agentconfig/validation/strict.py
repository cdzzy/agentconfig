"""
Optional Pydantic v2 strict-mode validation for AgentConfig.

The package ships two validation modes:

- ``lenient`` (default) — the built-in, zero-dependency JSON Schema
  walker in ``agentconfig.validation.validator``.
- ``strict`` — Pydantic v2 models configured with ``strict=True`` and
  ``extra="forbid"``. On top of everything the lenient mode enforces,
  strict mode:

  * reports **every** violation at once (the built-in walker stops at
    the first type mismatch on a given subtree);
  * gives precise pydantic error locations and error types
    ("missing", "string_type", "greater_than_equal", ...);
  * validates **without any silent type coercion** ("20" never becomes
    20, "yes" never becomes True), so what you validated is exactly
    what was in the file;
  * returns a typed model instance (``result.model``) you can reuse at
    runtime — attribute access instead of dict spelunking.

Pydantic is an optional dependency::

    pip install "cdzzy-agentconfig[strict]"

When pydantic is missing, strict-mode requests fall back to the
built-in validator and the result carries an explanatory note, so
existing pipelines never hard-fail on an optional extra.

Example::

    from agentconfig.validation import Strictness, validate_dict

    result = validate_dict({"name": "My Agent", "max_turns": 20},
                           mode=Strictness.STRICT)
    if result.valid:
        print(result.model.max_turns)  # typed access to the config
"""

from __future__ import annotations

import enum
from typing import Any, List, Optional

# ── Mode selection ───────────────────────────────────────────────────────


class Strictness(str, enum.Enum):
    """Validation mode selector.

    ``LENIENT`` — built-in JSON Schema walker (default, zero deps).
    ``STRICT`` — Pydantic v2 strict models (optional dependency).
    """

    LENIENT = "lenient"
    STRICT = "strict"


def normalize_mode(mode: Optional[Any] = None) -> Strictness:
    """Coerce a mode argument (None / str / Strictness) into a Strictness."""
    if mode is None:
        return Strictness.LENIENT
    if isinstance(mode, Strictness):
        return mode
    try:
        return Strictness(str(mode).lower())
    except ValueError:
        raise ValueError(
            f"Unknown validation mode: {mode!r}. Use 'lenient' or 'strict'."
        ) from None


# ── Optional pydantic import ─────────────────────────────────────────────

try:  # pragma: no cover - exercised indirectly via pydantic_available()
    from typing import Annotated, Dict, Literal, Union

    from pydantic import (
        BaseModel,
        ConfigDict,
        Field,
    )
    from pydantic import (
        ValidationError as PydanticValidationError,
    )

    _HAS_PYDANTIC = True
except ImportError:  # pragma: no cover
    _HAS_PYDANTIC = False


def pydantic_available() -> bool:
    """Return True when the optional pydantic v2 dependency is importable."""
    return _HAS_PYDANTIC


# ── Strict models (mirror of schemas/agent-config.schema.json) ───────────

if _HAS_PYDANTIC:

    class _StrictModel(BaseModel):
        """Shared config: strict typing, unknown fields rejected."""

        model_config = ConfigDict(strict=True, extra="forbid")

    _Tone = Literal[
        "professional", "friendly", "formal", "casual", "empathetic", "concise"
    ]
    _Domain = Literal[
        "customer_service", "sales", "hr", "finance",
        "it_support", "legal", "marketing", "general",
    ]
    _Provider = Literal[
        "openai", "anthropic", "ollama", "azure",
        "google", "mistral", "cohere", "custom",
    ]
    _ConstraintType = Literal[
        "forbidden_topic", "forbidden_keyword", "max_length", "min_length",
        "required_keyword", "tone_check", "escalation", "semantic_judge",
        "custom",
    ]
    _ConstraintAction = Literal["block", "warn", "replace", "escalate"]

    # JSON Schema "number" accepts both ints and floats; strict mode
    # must not reject temperature: 1 just because it parsed as an int.
    _Number = Union[int, float]

    class AgentIntentModel(_StrictModel):
        """``definitions/AgentIntent`` — structured business intent."""

        name: Annotated[str, Field(min_length=1)]
        purpose: Optional[str] = None
        audience: Optional[str] = None
        domain: Optional[_Domain] = None
        tone: Optional[List[_Tone]] = None
        language: Optional[str] = None
        actions_allowed: Optional[List[str]] = None
        actions_forbidden: Optional[List[str]] = None
        topics_forbidden: Optional[List[str]] = None
        escalation_triggers: Optional[List[str]] = None
        max_turns: Optional[Annotated[int, Field(ge=1, le=1000)]] = None
        require_confirmation: Optional[List[str]] = None
        goals: Optional[List[str]] = None

    class ModelConfigModel(_StrictModel):
        """``definitions/ModelConfig`` — LLM model configuration."""

        provider: Optional[_Provider] = None
        model: Optional[str] = None
        temperature: Optional[Annotated[_Number, Field(ge=0, le=2)]] = None
        max_tokens: Optional[Annotated[int, Field(ge=1, le=128000)]] = None
        top_p: Optional[Annotated[_Number, Field(ge=0, le=1)]] = None
        timeout_seconds: Optional[Annotated[int, Field(ge=1, le=600)]] = None
        api_base: Optional[str] = None

    class ConstraintModel(_StrictModel):
        """``definitions/Constraint`` — a single business rule."""

        id: Annotated[str, Field(min_length=1)]
        type: _ConstraintType
        description: Annotated[str, Field(min_length=1)]
        action: Optional[_ConstraintAction] = None
        fallback_message: Optional[str] = None
        keywords: Optional[List[str]] = None
        pattern: Optional[str] = None
        max_chars: Optional[Annotated[int, Field(ge=0)]] = None
        min_chars: Optional[Annotated[int, Field(ge=0)]] = None

    class MCPServerConfigModel(_StrictModel):
        """``definitions/MCPServerConfig`` — one MCP server declaration."""

        name: Annotated[str, Field(min_length=1)]
        command: Optional[str] = None
        args: Optional[List[str]] = None
        env: Optional[Dict[str, str]] = None
        url: Optional[str] = None
        description: Optional[str] = None
        tools: Optional[List[str]] = None

    class ToolPolicyModel(_StrictModel):
        """``definitions/ToolPolicy`` — MCP tool allow/block policy."""

        allowed_tools: Optional[List[str]] = None
        blocked_tools: Optional[List[str]] = None
        auto_approve: Optional[bool] = None
        require_confirmation: Optional[List[str]] = None

    class AgentConfigModel(_StrictModel):
        """Top-level AgentConfig — mirrors the schema root object."""

        config_id: Optional[Annotated[str, Field(min_length=1, max_length=36)]] = None
        name: Annotated[str, Field(min_length=1, max_length=200)]
        version: Optional[Annotated[str, Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")]] = None
        created_at: Optional[str] = None
        description: Optional[Annotated[str, Field(max_length=1000)]] = None
        system_prompt: Optional[str] = None
        intent: Optional[AgentIntentModel] = None
        model: Optional[ModelConfigModel] = None
        constraints: Optional[List[ConstraintModel]] = None
        tools_enabled: Optional[List[str]] = None
        tools_disabled: Optional[List[str]] = None
        max_turns: Optional[Annotated[int, Field(ge=1, le=1000)]] = None
        stream: Optional[bool] = None
        log_enabled: Optional[bool] = None
        audit_enabled: Optional[bool] = None
        metadata: Optional[Dict[str, Any]] = None
        mcp_servers: Optional[List[MCPServerConfigModel]] = None
        tool_policy: Optional[ToolPolicyModel] = None


# ── Validation entry point ────────────────────────────────────────────────


def _pydantic_errors_to_validation_errors(exc: "PydanticValidationError") -> List[Any]:
    """Translate pydantic's error list into agentconfig ValidationError items."""
    from agentconfig.validation.validator import ValidationError

    errors: List[ValidationError] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()))
        errors.append(
            ValidationError(
                path=loc,
                message=err.get("msg", "invalid value"),
                value=err.get("input"),
            )
        )
    return errors


def validate_dict_strict(data: dict) -> Any:
    """Validate a config dict with pydantic v2 strict models.

    Returns a ValidationResult whose ``model`` attribute holds the typed
    AgentConfigModel instance on success. If pydantic is not installed,
    falls back to the built-in lenient validator and records a note.
    """
    from agentconfig.validation.validator import ValidationResult, validate_dict

    if not _HAS_PYDANTIC:
        result = validate_dict(data)
        result.mode = "lenient"
        result.notes.append(
            "pydantic is not installed — strict mode fell back to the built-in "
            "validator. Install with: pip install 'cdzzy-agentconfig[strict]'"
        )
        return result

    try:
        model = AgentConfigModel.model_validate(data)
    except PydanticValidationError as exc:
        return ValidationResult(
            valid=False,
            errors=_pydantic_errors_to_validation_errors(exc),
            mode="strict",
        )

    result = ValidationResult(valid=True, errors=[], mode="strict")
    result.model = model
    return result


__all__ = [
    "Strictness",
    "normalize_mode",
    "pydantic_available",
    "validate_dict_strict",
]
