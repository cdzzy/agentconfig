"""
Config Generator — produces a final AgentConfig from intent + constraints.

AgentConfig is the single artifact passed to the runtime executor.
It contains everything needed to run the agent: system prompt, constraints,
model settings, tool permissions, and metadata.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from agentconfig.semantic.intent import AgentIntent
from agentconfig.semantic.constraint import ConstraintEngine, Constraint, ConstraintType, ConstraintAction


@dataclass
class ModelConfig:
    """LLM model configuration."""
    provider: str = "openai"          # openai, anthropic, ollama, azure, etc.
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 1.0
    timeout_seconds: int = 30
    api_base: Optional[str] = None    # For custom endpoints / Ollama

    def to_dict(self) -> dict:
        return {
            "provider":         self.provider,
            "model":            self.model,
            "temperature":      self.temperature,
            "max_tokens":       self.max_tokens,
            "top_p":            self.top_p,
            "timeout_seconds":  self.timeout_seconds,
            "api_base":         self.api_base,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ModelConfig":
        obj = cls()
        obj.provider        = d.get("provider", "openai")
        obj.model           = d.get("model", "gpt-4o-mini")
        obj.temperature     = d.get("temperature", 0.7)
        obj.max_tokens      = d.get("max_tokens", 1024)
        obj.top_p           = d.get("top_p", 1.0)
        obj.timeout_seconds = d.get("timeout_seconds", 30)
        obj.api_base        = d.get("api_base")
        return obj


@dataclass
class AgentConfig:
    """
    Complete, executable configuration for an AI agent.

    This is the artifact produced by ConfigGenerator and consumed by AgentExecutor.
    It can be serialized to JSON, stored, versioned, and shared.
    """

    # Identity
    config_id:   str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name:        str = "My Agent"
    version:     str = "1.0.0"
    created_at:  str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    description: str = ""

    # Core behavior
    system_prompt: str = ""
    intent:        Optional[AgentIntent] = None

    # Model
    model: ModelConfig = field(default_factory=ModelConfig)

    # Constraints (serialized list of dicts)
    constraints: List[dict] = field(default_factory=list)

    # Tool permissions
    tools_enabled:  List[str] = field(default_factory=list)
    tools_disabled: List[str] = field(default_factory=list)

    # Operational settings
    max_turns:     int  = 20
    stream:        bool = False
    log_enabled:   bool = True
    audit_enabled: bool = True

    # MCP server declarations (Issue #4)
    mcp_servers: List[dict] = field(default_factory=list)
    tool_policy: Optional[dict] = None  # ToolPolicy as dict

    # Custom metadata from business user
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_constraint_engine(self) -> ConstraintEngine:
        return ConstraintEngine.from_list(self.constraints)

    def to_dict(self) -> dict:
        d = {
            "config_id":    self.config_id,
            "name":         self.name,
            "version":      self.version,
            "created_at":   self.created_at,
            "description":  self.description,
            "system_prompt": self.system_prompt,
            "intent":       self.intent.to_dict() if self.intent else None,
            "model":        self.model.to_dict(),
            "constraints":  self.constraints,
            "tools_enabled":  self.tools_enabled,
            "tools_disabled": self.tools_disabled,
            "max_turns":    self.max_turns,
            "stream":       self.stream,
            "log_enabled":  self.log_enabled,
            "audit_enabled": self.audit_enabled,
            "metadata":     self.metadata,
        }
        if self.mcp_servers:
            d["mcp_servers"] = self.mcp_servers
        if self.tool_policy is not None:
            d["tool_policy"] = self.tool_policy
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "AgentConfig":
        cfg = cls()
        cfg.config_id    = d.get("config_id", cfg.config_id)
        cfg.name         = d.get("name", "My Agent")
        cfg.version      = d.get("version", "1.0.0")
        cfg.created_at   = d.get("created_at", cfg.created_at)
        cfg.description  = d.get("description", "")
        cfg.system_prompt = d.get("system_prompt", "")
        if d.get("intent"):
            cfg.intent   = AgentIntent.from_dict(d["intent"])
        if d.get("model"):
            cfg.model    = ModelConfig.from_dict(d["model"])
        cfg.constraints  = d.get("constraints", [])
        cfg.tools_enabled  = d.get("tools_enabled", [])
        cfg.tools_disabled = d.get("tools_disabled", [])
        cfg.max_turns    = d.get("max_turns", 20)
        cfg.stream       = d.get("stream", False)
        cfg.log_enabled  = d.get("log_enabled", True)
        cfg.audit_enabled = d.get("audit_enabled", True)
        cfg.mcp_servers   = d.get("mcp_servers", [])
        cfg.tool_policy   = d.get("tool_policy")
        cfg.metadata     = d.get("metadata", {})
        return cfg

    @classmethod
    def from_json(cls, s: str) -> "AgentConfig":
        return cls.from_dict(json.loads(s))

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "AgentConfig":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())

    # ── A2A & MCP convenience methods ──────────────────────────────────────

    def to_a2a_card(self, endpoint: str = "", **kwargs) -> "A2ACard":
        """
        Generate an A2A Agent Card from this config.

        Args:
            endpoint: The agent's public URL.
            **kwargs: Additional A2A card options (api_version, provider, etc.)

        Returns:
            A2ACard instance.

        Example::

            config = AgentConfig(name="ResearchAgent")
            card = config.to_a2a_card(endpoint="https://agent.example.com")
            card.save(".well-known/agent.json")
        """
        from agentconfig.a2a import generate_a2a_card
        return generate_a2a_card(self, endpoint=endpoint, **kwargs)

    def get_mcp_router(self) -> "MCPRouter":
        """
        Get an MCP router for this config's MCP servers and tool policy.

        Returns:
            MCPRouter instance.

        Example::

            config = AgentConfig(name="Agent", mcp_servers=[...], tool_policy={...})
            router = config.get_mcp_router()
            print(router.get_allowed_tools())
        """
        from agentconfig.mcp import MCPServerConfig, ToolPolicy, MCPRouter
        servers = [MCPServerConfig.from_dict(s) for s in self.mcp_servers]
        policy = ToolPolicy.from_dict(self.tool_policy) if self.tool_policy else ToolPolicy()
        return MCPRouter(mcp_servers=servers, tool_policy=policy)


class ConfigGenerator:
    """
    Generates an AgentConfig from an AgentIntent and optional extra constraints.

    Usage::

        from agentconfig.semantic.intent import IntentParser
        from agentconfig.semantic.config_gen import ConfigGenerator, ModelConfig

        parser = IntentParser()
        intent = parser.parse(
            "Handle customer complaints politely. Never mention pricing.",
            name="Support Bot"
        )

        gen = ConfigGenerator()
        config = gen.generate(
            intent=intent,
            model=ModelConfig(model="gpt-4o", temperature=0.3),
        )
        print(config.to_json())
    """

    def generate(
        self,
        intent: AgentIntent,
        model: Optional[ModelConfig] = None,
        extra_constraints: Optional[List[Constraint]] = None,
        version: str = "1.0.0",
    ) -> AgentConfig:

        cfg = AgentConfig(
            name=intent.name,
            version=version,
            description=intent.purpose[:200] if intent.purpose else "",
        )

        # System prompt from intent
        cfg.system_prompt = intent.to_system_prompt()
        cfg.intent = intent
        cfg.max_turns = intent.max_turns

        # Model config
        cfg.model = model or ModelConfig()

        # Auto-generate constraints from intent
        constraints: List[Constraint] = []

        for i, topic in enumerate(intent.topics_forbidden):
            constraints.append(Constraint(
                id=f"auto-forbidden-topic-{i}",
                type=ConstraintType.FORBIDDEN_TOPIC,
                description=f"Forbidden topic: {topic}",
                keywords=[topic],
                action=ConstraintAction.BLOCK,
            ))

        for i, action in enumerate(intent.actions_forbidden):
            constraints.append(Constraint(
                id=f"auto-forbidden-action-{i}",
                type=ConstraintType.FORBIDDEN_KEYWORD,
                description=f"Forbidden action/content: {action}",
                keywords=action.split(),
                action=ConstraintAction.BLOCK,
            ))

        # Add extra constraints
        if extra_constraints:
            constraints.extend(extra_constraints)

        cfg.constraints = [c.to_dict() for c in constraints]

        return cfg
