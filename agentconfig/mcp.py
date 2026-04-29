"""
MCP Tool Declarations — Define MCP servers and tool policies in agent config.

MCP (Model Context Protocol) is the de facto standard for agent-tool integration.
This module adds MCP server declarations and tool policies to AgentConfig.

Usage::

    from agentconfig.mcp import MCPServerConfig, ToolPolicy, MCPRouter

    # Define MCP servers
    config = AgentConfig(
        name="ResearchAgent",
        mcp_servers=[
            MCPServerConfig(
                name="web-search",
                command="npx",
                args=["-y", "@anthropic/mcp-server-brave"],
                env={"BRAVE_API_KEY": "${BRAVE_API_KEY}"},
            ),
            MCPServerConfig(
                name="filesystem",
                command="npx",
                args=["-y", "@anthropic/mcp-server-filesystem", "/data"],
            ),
        ],
        tool_policy=ToolPolicy(
            allowed_tools=["web-search:brave_web_search", "filesystem:read_file"],
            blocked_tools=["filesystem:write_file"],
            auto_approve=True,
        ),
    )

    # Get all available tools from MCP servers
    router = MCPRouter(config)
    all_tools = router.get_all_tools()
    allowed = router.get_allowed_tools()
    blocked = router.get_blocked_tools()

References:
    - MCP spec: https://modelcontextprotocol.io
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class MCPServerConfig:
    """
    Configuration for a single MCP server.

    An MCP server provides tools that an agent can use. This config
    defines how to start and connect to the server.
    """

    name: str = ""
    command: str = ""
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None  # For SSE-based MCP servers
    description: str = ""
    tools: List[str] = field(default_factory=list)  # Tool names this server provides

    def to_dict(self) -> dict:
        result: Dict[str, Any] = {
            "name": self.name,
            "command": self.command,
        }
        if self.args:
            result["args"] = self.args
        if self.env:
            result["env"] = self.env
        if self.url:
            result["url"] = self.url
        if self.description:
            result["description"] = self.description
        if self.tools:
            result["tools"] = self.tools
        return result

    @classmethod
    def from_dict(cls, d: dict) -> "MCPServerConfig":
        return cls(
            name=d.get("name", ""),
            command=d.get("command", ""),
            args=d.get("args", []),
            env=d.get("env", {}),
            url=d.get("url"),
            description=d.get("description", ""),
            tools=d.get("tools", []),
        )


@dataclass
class ToolPolicy:
    """
    Policy controlling which MCP tools an agent is allowed or blocked from using.

    Tool names use the format ``server_name:tool_name`` (e.g. ``web-search:brave_web_search``).
    """

    allowed_tools: List[str] = field(default_factory=list)
    blocked_tools: List[str] = field(default_factory=list)
    auto_approve: bool = False  # Auto-approve tool calls without human confirmation
    require_confirmation: List[str] = field(default_factory=list)  # Tools requiring human approval

    def to_dict(self) -> dict:
        result: Dict[str, Any] = {}
        if self.allowed_tools:
            result["allowed_tools"] = self.allowed_tools
        if self.blocked_tools:
            result["blocked_tools"] = self.blocked_tools
        if self.auto_approve:
            result["auto_approve"] = self.auto_approve
        if self.require_confirmation:
            result["require_confirmation"] = self.require_confirmation
        return result

    @classmethod
    def from_dict(cls, d: dict) -> "ToolPolicy":
        if not d:
            return cls()
        return cls(
            allowed_tools=d.get("allowed_tools", []),
            blocked_tools=d.get("blocked_tools", []),
            auto_approve=d.get("auto_approve", False),
            require_confirmation=d.get("require_confirmation", []),
        )

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a specific tool is allowed by this policy."""
        # Blocked tools take precedence
        if tool_name in self.blocked_tools:
            return False
        # If allowed_tools is empty, everything not blocked is allowed
        if not self.allowed_tools:
            return True
        return tool_name in self.allowed_tools

    def needs_confirmation(self, tool_name: str) -> bool:
        """Check if a tool requires human confirmation before use."""
        if tool_name in self.require_confirmation:
            return True
        if self.allowed_tools and tool_name not in self.allowed_tools:
            return True
        return not self.auto_approve


class MCPRouter:
    """
    Router that resolves tool availability from MCP servers and tool policies.

    Combines MCP server declarations with tool policies to determine
    which tools are available, allowed, or blocked for an agent.
    """

    def __init__(
        self,
        mcp_servers: Optional[List[MCPServerConfig]] = None,
        tool_policy: Optional[ToolPolicy] = None,
    ):
        self.mcp_servers = mcp_servers or []
        self.tool_policy = tool_policy or ToolPolicy()

    def get_all_tools(self) -> List[str]:
        """Get all tools from all MCP servers (qualified as server:tool)."""
        tools: List[str] = []
        for server in self.mcp_servers:
            if server.tools:
                for tool in server.tools:
                    tools.append(f"{server.name}:{tool}")
            else:
                tools.append(f"{server.name}:*")
        return tools

    def get_allowed_tools(self) -> List[str]:
        """Get all tools that are allowed by the tool policy."""
        return [t for t in self.get_all_tools() if self.tool_policy.is_tool_allowed(t)]

    def get_blocked_tools(self) -> List[str]:
        """Get all tools that are blocked by the tool policy."""
        return [t for t in self.get_all_tools() if not self.tool_policy.is_tool_allowed(t)]

    def get_tools_requiring_confirmation(self) -> List[str]:
        """Get all allowed tools that require human confirmation."""
        return [
            t for t in self.get_allowed_tools()
            if self.tool_policy.needs_confirmation(t)
        ]

    def get_server_config(self, server_name: str) -> Optional[MCPServerConfig]:
        """Get the config for a specific MCP server by name."""
        for server in self.mcp_servers:
            if server.name == server_name:
                return server
        return None

    def resolve_tool(self, qualified_name: str) -> Optional[dict]:
        """
        Resolve a qualified tool name (server:tool) to its server config.

        Returns dict with server info and tool name, or None if not found.
        """
        if ":" not in qualified_name:
            return None
        server_name, tool_name = qualified_name.split(":", 1)
        server = self.get_server_config(server_name)
        if not server:
            return None
        return {
            "server_name": server_name,
            "tool_name": tool_name,
            "command": server.command,
            "args": server.args,
            "allowed": self.tool_policy.is_tool_allowed(qualified_name),
            "needs_confirmation": self.tool_policy.needs_confirmation(qualified_name),
        }
