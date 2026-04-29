"""
A2A Agent Card Generator — Generate Google A2A protocol agent cards from AgentConfig.

A2A (Agent-to-Agent) protocol uses agent.json cards for service discovery.
This module auto-generates compliant cards from existing AgentConfig instances.

Usage::

    from agentconfig.a2a import generate_a2a_card, A2ACard

    # Generate from config
    card = generate_a2a_card(config, endpoint="https://my-agent.example.com")

    # Export to file
    card.save(".well-known/agent.json")

    # Or get as dict/JSON
    card_dict = card.to_dict()
    card_json = card.to_json()

References:
    - Google A2A spec: https://github.com/google/A2A
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agentconfig.semantic.config_gen import AgentConfig


@dataclass
class A2ASkill:
    """A skill offered by an agent in its A2A card."""

    id: str = ""
    name: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "A2ASkill":
        return cls(
            id=d.get("id", ""),
            name=d.get("name", ""),
            description=d.get("description", ""),
        )


@dataclass
class A2ACard:
    """
    A2A Agent Card — Google's Agent-to-Agent protocol service discovery document.

    This is the JSON document served at ``/.well-known/agent.json`` that enables
    other agents to discover and interact with this agent.
    """

    name: str = ""
    description: str = ""
    url: str = ""
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    skills: List[A2ASkill] = field(default_factory=list)
    provider: Optional[Dict[str, str]] = None
    documentation_url: str = ""
    api_version: str = "a2a/v1"

    def to_dict(self) -> dict:
        result: Dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "version": self.version,
            "capabilities": self.capabilities,
            "skills": [s.to_dict() for s in self.skills],
            "apiVersion": self.api_version,
        }
        if self.provider:
            result["provider"] = self.provider
        if self.documentation_url:
            result["documentationUrl"] = self.documentation_url
        return result

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "A2ACard":
        skills = [A2ASkill.from_dict(s) for s in d.get("skills", [])]
        return cls(
            name=d.get("name", ""),
            description=d.get("description", ""),
            url=d.get("url", ""),
            version=d.get("version", "1.0.0"),
            capabilities=d.get("capabilities", []),
            skills=skills,
            provider=d.get("provider"),
            documentation_url=d.get("documentationUrl", ""),
            api_version=d.get("apiVersion", "a2a/v1"),
        )

    def save(self, path: str) -> None:
        """Save the A2A card to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, path: str) -> "A2ACard":
        """Load an A2A card from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))


def generate_a2a_card(
    config: AgentConfig,
    endpoint: str = "",
    api_version: str = "a2a/v1",
    documentation_url: str = "",
    provider: Optional[Dict[str, str]] = None,
) -> A2ACard:
    """
    Generate an A2A Agent Card from an AgentConfig.

    Maps AgentConfig fields to A2A card fields:
    - name → name
    - description → description
    - tools_enabled → capabilities
    - constraints → skills (constraint descriptions as defensive skills)
    - intent → enhanced description and capabilities

    Args:
        config: The AgentConfig to generate a card from.
        endpoint: The agent's public URL (e.g. ``https://my-agent.example.com``).
        api_version: A2A protocol version (default: ``a2a/v1``).
        documentation_url: Optional URL to agent documentation.
        provider: Optional provider info dict (e.g. ``{"organization": "Acme"}``).

    Returns:
        A2ACard instance ready for export.

    Example::

        from agentconfig import AgentConfig
        from agentconfig.a2a import generate_a2a_card

        config = AgentConfig(name="ResearchAgent", description="Web researcher")
        card = generate_a2a_card(config, endpoint="https://agent.example.com")
        card.save(".well-known/agent.json")
    """
    # Build capabilities from tools_enabled
    capabilities = list(config.tools_enabled)

    # Enhance capabilities from intent
    if config.intent:
        if config.intent.domain and config.intent.domain.value not in capabilities:
            capabilities.append(f"domain:{config.intent.domain.value}")
        for action in config.intent.actions_allowed:
            if action not in capabilities:
                capabilities.append(action)

    # Build skills from constraints (as protective capabilities)
    skills: List[A2ASkill] = []
    for i, constraint in enumerate(config.constraints):
        skill = A2ASkill(
            id=constraint.get("id", f"skill-{i}"),
            name=constraint.get("description", f"Skill {i}")[:100],
            description=constraint.get("description", ""),
        )
        skills.append(skill)

    # Also add tools as skills
    for tool_name in config.tools_enabled:
        skills.append(A2ASkill(
            id=f"tool-{tool_name}",
            name=tool_name,
            description=f"Tool: {tool_name}",
        ))

    # Build description
    description = config.description
    if config.intent and config.intent.purpose:
        if description:
            description = f"{description}. {config.intent.purpose}"
        else:
            description = config.intent.purpose

    # Build URL
    url = f"{endpoint.rstrip('/')}/.well-known/agent.json" if endpoint else ""

    return A2ACard(
        name=config.name,
        description=description,
        url=url,
        version=config.version,
        capabilities=capabilities,
        skills=skills,
        provider=provider,
        documentation_url=documentation_url,
        api_version=api_version,
    )
