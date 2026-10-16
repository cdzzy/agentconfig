"""
AgentConfig — Business-semantic driven Agent configuration system.

The missing layer between business users and AI agents.
"""

__author__ = "cdzzy"

from agentconfig.a2a import A2ACard, A2ASkill, generate_a2a_card
from agentconfig.adapters.frameworks import (
    ConstraintBlocked,
    enforce_response,
    wrap_autogen_reply,
    wrap_crewai_agent,
    wrap_langgraph_node,
)
from agentconfig.hotreload import (
    ConfigWatcher,
    RuntimeConfigStore,
    create_reload_blueprint,
    watch_config,
)
from agentconfig.loader import list_formats, load_config, save_config
from agentconfig.mcp import MCPRouter, MCPServerConfig, ToolPolicy, substitute_env
from agentconfig.portable import AgentDir, init_agent_dir, load_agent_dir, save_agent_dir
from agentconfig.runtime.executor import AgentExecutor
from agentconfig.runtime.monitor import AgentMonitor, RunRecord
from agentconfig.semantic.config_gen import AgentConfig, ConfigGenerator
from agentconfig.semantic.constraint import Constraint, ConstraintEngine, ConstraintType
from agentconfig.semantic.intent import AgentIntent, IntentParser
from agentconfig.semantic.judge import JudgeVerdict, LLMJudge, semantic_judge_constraint
from agentconfig.validation import (
    ValidationError,
    ValidationResult,
    get_schema,
    validate_config,
    validate_dict,
)
from agentconfig.versioning import ConfigVersion, ConfigVersionManager, diff_configs, diff_dicts


def _version_from_pyproject() -> str:
    """Read the canonical version from the adjacent pyproject.toml (PEP 621)."""
    try:
        import re
        from pathlib import Path

        pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
        match = re.search(
            r'^version\s*=\s*"([^"]+)"',
            pyproject.read_text(encoding="utf-8"),
            re.M,
        )
        return match.group(1) if match else ""
    except Exception:
        return ""


def _version_from_metadata() -> str:
    """Fall back to the installed distribution metadata (regular installs)."""
    try:
        from importlib.metadata import version as _pkg_version

        return _pkg_version("cdzzy-agentconfig")
    except Exception:
        return ""


# pyproject.toml is the single source of truth in a source checkout / editable
# install, so __version__ can never drift from the declared version; regular
# installed copies (no adjacent pyproject.toml) fall back to dist metadata.
__version__ = _version_from_pyproject() or _version_from_metadata() or "0.0.0"

__all__ = [
    "IntentParser",
    "AgentIntent",
    "ConstraintEngine",
    "Constraint",
    "ConstraintType",
    "ConfigGenerator",
    "AgentConfig",
    "LLMJudge",
    "JudgeVerdict",
    "semantic_judge_constraint",
    "AgentExecutor",
    "AgentMonitor",
    "RunRecord",
    "validate_config",
    "validate_dict",
    "get_schema",
    "ValidationResult",
    "ValidationError",
    "load_config",
    "save_config",
    "list_formats",
    "A2ACard",
    "A2ASkill",
    "generate_a2a_card",
    "MCPServerConfig",
    "ToolPolicy",
    "MCPRouter",
    "substitute_env",
    "AgentDir",
    "load_agent_dir",
    "save_agent_dir",
    "init_agent_dir",
    "ConfigVersionManager",
    "ConfigVersion",
    "diff_configs",
    "diff_dicts",
    "ConfigWatcher",
    "watch_config",
    "RuntimeConfigStore",
    "create_reload_blueprint",
    "ConstraintBlocked",
    "enforce_response",
    "wrap_autogen_reply",
    "wrap_crewai_agent",
    "wrap_langgraph_node",
]
