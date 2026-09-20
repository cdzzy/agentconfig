"""
AgentConfig — Business-semantic driven Agent configuration system.

The missing layer between business users and AI agents.
"""

__version__ = "2.3.0"
__author__ = "cdzzy"

from agentconfig.semantic.intent import IntentParser, AgentIntent
from agentconfig.semantic.constraint import ConstraintEngine, Constraint, ConstraintType
from agentconfig.semantic.config_gen import ConfigGenerator, AgentConfig
from agentconfig.semantic.judge import LLMJudge, JudgeVerdict, semantic_judge_constraint
from agentconfig.runtime.executor import AgentExecutor
from agentconfig.runtime.monitor import AgentMonitor, RunRecord
from agentconfig.validation import validate_config, validate_dict, get_schema, ValidationResult, ValidationError
from agentconfig.loader import load_config, save_config, list_formats
from agentconfig.a2a import A2ACard, A2ASkill, generate_a2a_card
from agentconfig.mcp import MCPServerConfig, ToolPolicy, MCPRouter, substitute_env
from agentconfig.portable import AgentDir, load_agent_dir, save_agent_dir, init_agent_dir
from agentconfig.versioning import ConfigVersionManager, ConfigVersion, diff_configs, diff_dicts
from agentconfig.hotreload import ConfigWatcher, watch_config, RuntimeConfigStore, create_reload_blueprint
from agentconfig.adapters.frameworks import (
    ConstraintBlocked,
    enforce_response,
    wrap_autogen_reply,
    wrap_crewai_agent,
    wrap_langgraph_node,
)

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
