"""
Tests for A2A Agent Card generation (Issue #3) and MCP tool declarations (Issue #4).
"""

import pytest
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from agentconfig.a2a import A2ACard, A2ASkill, generate_a2a_card
from agentconfig.mcp import MCPServerConfig, ToolPolicy, MCPRouter
from agentconfig.semantic.config_gen import AgentConfig, ModelConfig, ConfigGenerator
from agentconfig.semantic.intent import IntentParser


# ── A2A Card Tests (Issue #3) ─────────────────────────────────────────────

class TestA2ASkill:
    def test_to_dict(self):
        skill = A2ASkill(id="web-search", name="Web Search", description="Search the web")
        d = skill.to_dict()
        assert d["id"] == "web-search"
        assert d["name"] == "Web Search"

    def test_from_dict(self):
        d = {"id": "s1", "name": "Skill", "description": "A skill"}
        skill = A2ASkill.from_dict(d)
        assert skill.id == "s1"
        assert skill.name == "Skill"

    def test_roundtrip(self):
        skill = A2ASkill(id="t1", name="Test", description="Test skill")
        restored = A2ASkill.from_dict(skill.to_dict())
        assert restored.id == skill.id
        assert restored.name == skill.name


class TestA2ACard:
    def test_to_dict(self):
        card = A2ACard(
            name="TestAgent",
            description="A test agent",
            url="https://example.com/.well-known/agent.json",
            capabilities=["web-search", "summarization"],
        )
        d = card.to_dict()
        assert d["name"] == "TestAgent"
        assert d["capabilities"] == ["web-search", "summarization"]
        assert d["apiVersion"] == "a2a/v1"

    def test_from_dict(self):
        d = {
            "name": "Agent",
            "description": "Test",
            "url": "https://example.com/.well-known/agent.json",
            "version": "2.0.0",
            "capabilities": ["search"],
            "skills": [{"id": "s1", "name": "Search", "description": "Search the web"}],
            "apiVersion": "a2a/v1",
        }
        card = A2ACard.from_dict(d)
        assert card.name == "Agent"
        assert card.version == "2.0.0"
        assert len(card.skills) == 1
        assert card.skills[0].name == "Search"

    def test_to_json(self):
        card = A2ACard(name="JSONAgent", description="Test")
        j = card.to_json()
        data = json.loads(j)
        assert data["name"] == "JSONAgent"

    def test_save_and_load(self, tmp_path):
        card = A2ACard(
            name="FileAgent",
            description="Saved to file",
            url="https://example.com/.well-known/agent.json",
            capabilities=["search"],
        )
        path = str(tmp_path / "agent.json")
        card.save(path)
        loaded = A2ACard.load(path)
        assert loaded.name == "FileAgent"
        assert loaded.capabilities == ["search"]

    def test_provider_in_dict(self):
        card = A2ACard(
            name="Agent",
            provider={"organization": "Acme Corp"},
        )
        d = card.to_dict()
        assert d["provider"]["organization"] == "Acme Corp"

    def test_no_provider_omitted(self):
        card = A2ACard(name="Agent")
        d = card.to_dict()
        assert "provider" not in d


class TestGenerateA2ACard:
    def test_basic_generation(self):
        config = AgentConfig(name="ResearchAgent", description="Web researcher")
        card = generate_a2a_card(config, endpoint="https://agent.example.com")
        assert card.name == "ResearchAgent"
        assert card.description == "Web researcher"
        assert "agent.example.com" in card.url

    def test_capabilities_from_tools(self):
        config = AgentConfig(
            name="Agent",
            tools_enabled=["web_search", "calculator"],
        )
        card = generate_a2a_card(config)
        assert "web_search" in card.capabilities
        assert "calculator" in card.capabilities

    def test_skills_from_constraints(self):
        config = AgentConfig(
            name="Agent",
            constraints=[{
                "id": "no-pricing",
                "type": "forbidden_keyword",
                "description": "No pricing info",
                "keywords": ["price"],
                "action": "block",
            }],
        )
        card = generate_a2a_card(config)
        skill_names = [s.name for s in card.skills]
        assert "No pricing info" in skill_names

    def test_skills_from_tools(self):
        config = AgentConfig(
            name="Agent",
            tools_enabled=["web_search"],
        )
        card = generate_a2a_card(config)
        skill_ids = [s.id for s in card.skills]
        assert "tool-web_search" in skill_ids

    def test_with_intent(self):
        parser = IntentParser()
        intent = parser.parse("Handle customer support politely.", name="SupportBot")
        gen = ConfigGenerator()
        config = gen.generate(intent)
        card = generate_a2a_card(config, endpoint="https://support.example.com")
        assert card.name == "SupportBot"
        assert card.description != ""

    def test_custom_api_version(self):
        config = AgentConfig(name="Agent")
        card = generate_a2a_card(config, api_version="a2a/v2")
        assert card.api_version == "a2a/v2"

    def test_endpoint_url_format(self):
        config = AgentConfig(name="Agent")
        card = generate_a2a_card(config, endpoint="https://example.com/")
        assert card.url == "https://example.com/.well-known/agent.json"

    def test_empty_endpoint(self):
        config = AgentConfig(name="Agent")
        card = generate_a2a_card(config)
        assert card.url == ""

    def test_agent_config_to_a2a_card_method(self):
        config = AgentConfig(name="MethodAgent", description="Testing convenience method")
        card = config.to_a2a_card(endpoint="https://test.example.com")
        assert card.name == "MethodAgent"


# ── MCP Tests (Issue #4) ──────────────────────────────────────────────────

class TestMCPServerConfig:
    def test_to_dict(self):
        server = MCPServerConfig(
            name="web-search",
            command="npx",
            args=["-y", "@anthropic/mcp-server-brave"],
            env={"BRAVE_API_KEY": "${BRAVE_API_KEY}"},
        )
        d = server.to_dict()
        assert d["name"] == "web-search"
        assert d["command"] == "npx"
        assert d["args"] == ["-y", "@anthropic/mcp-server-brave"]
        assert d["env"]["BRAVE_API_KEY"] == "${BRAVE_API_KEY}"

    def test_from_dict(self):
        d = {
            "name": "filesystem",
            "command": "npx",
            "args": ["-y", "@anthropic/mcp-server-filesystem", "/data"],
            "tools": ["read_file", "write_file"],
        }
        server = MCPServerConfig.from_dict(d)
        assert server.name == "filesystem"
        assert server.tools == ["read_file", "write_file"]

    def test_roundtrip(self):
        server = MCPServerConfig(
            name="test",
            command="python",
            args=["-m", "mcp_server"],
            env={"KEY": "value"},
            tools=["tool1", "tool2"],
        )
        restored = MCPServerConfig.from_dict(server.to_dict())
        assert restored.name == server.name
        assert restored.args == server.args
        assert restored.tools == server.tools

    def test_url_based_server(self):
        server = MCPServerConfig(
            name="remote",
            url="https://mcp.example.com/sse",
        )
        d = server.to_dict()
        assert d["url"] == "https://mcp.example.com/sse"

    def test_minimal_dict(self):
        """Only required fields are included in output."""
        server = MCPServerConfig(name="minimal", command="echo")
        d = server.to_dict()
        assert "name" in d
        assert "command" in d
        # Optional fields not included when empty
        assert "args" not in d or d.get("args") == []


class TestToolPolicy:
    def test_to_dict(self):
        policy = ToolPolicy(
            allowed_tools=["web-search:brave_web_search"],
            blocked_tools=["filesystem:write_file"],
            auto_approve=True,
        )
        d = policy.to_dict()
        assert d["allowed_tools"] == ["web-search:brave_web_search"]
        assert d["blocked_tools"] == ["filesystem:write_file"]
        assert d["auto_approve"] is True

    def test_from_dict(self):
        d = {
            "allowed_tools": ["s1:t1"],
            "blocked_tools": ["s2:t2"],
            "auto_approve": False,
            "require_confirmation": ["s3:t3"],
        }
        policy = ToolPolicy.from_dict(d)
        assert policy.allowed_tools == ["s1:t1"]
        assert policy.blocked_tools == ["s2:t2"]
        assert policy.require_confirmation == ["s3:t3"]

    def test_from_empty_dict(self):
        policy = ToolPolicy.from_dict({})
        assert policy.allowed_tools == []
        assert policy.blocked_tools == []

    def test_is_tool_allowed_empty_policy(self):
        """Empty policy allows everything not blocked."""
        policy = ToolPolicy()
        assert policy.is_tool_allowed("anything") is True

    def test_is_tool_allowed_with_allowlist(self):
        policy = ToolPolicy(allowed_tools=["web:search"])
        assert policy.is_tool_allowed("web:search") is True
        assert policy.is_tool_allowed("web:delete") is False

    def test_is_tool_blocked_takes_precedence(self):
        """Blocked list takes precedence over allowlist."""
        policy = ToolPolicy(
            allowed_tools=["web:search", "web:delete"],
            blocked_tools=["web:delete"],
        )
        assert policy.is_tool_allowed("web:search") is True
        assert policy.is_tool_allowed("web:delete") is False

    def test_needs_confirmation(self):
        policy = ToolPolicy(
            allowed_tools=["web:search"],
            require_confirmation=["web:search"],
            auto_approve=True,
        )
        assert policy.needs_confirmation("web:search") is True

    def test_auto_approve_skips_confirmation(self):
        policy = ToolPolicy(auto_approve=True)
        assert policy.needs_confirmation("any:tool") is False


class TestMCPRouter:
    def _make_router(self):
        servers = [
            MCPServerConfig(
                name="web-search",
                command="npx",
                args=["-y", "@anthropic/mcp-server-brave"],
                tools=["brave_web_search", "brave_suggest"],
            ),
            MCPServerConfig(
                name="filesystem",
                command="npx",
                args=["-y", "@anthropic/mcp-server-filesystem", "/data"],
                tools=["read_file", "write_file"],
            ),
        ]
        policy = ToolPolicy(
            allowed_tools=["web-search:brave_web_search", "filesystem:read_file"],
            blocked_tools=["filesystem:write_file"],
        )
        return MCPRouter(mcp_servers=servers, tool_policy=policy)

    def test_get_all_tools(self):
        router = self._make_router()
        tools = router.get_all_tools()
        assert "web-search:brave_web_search" in tools
        assert "filesystem:read_file" in tools
        assert "filesystem:write_file" in tools

    def test_get_allowed_tools(self):
        router = self._make_router()
        allowed = router.get_allowed_tools()
        assert "web-search:brave_web_search" in allowed
        assert "filesystem:read_file" in allowed
        assert "filesystem:write_file" not in allowed

    def test_get_blocked_tools(self):
        router = self._make_router()
        blocked = router.get_blocked_tools()
        assert "filesystem:write_file" in blocked
        assert "web-search:brave_web_search" not in blocked

    def test_get_server_config(self):
        router = self._make_router()
        server = router.get_server_config("web-search")
        assert server is not None
        assert server.command == "npx"

    def test_get_nonexistent_server(self):
        router = self._make_router()
        assert router.get_server_config("nonexistent") is None

    def test_resolve_tool(self):
        router = self._make_router()
        resolved = router.resolve_tool("web-search:brave_web_search")
        assert resolved is not None
        assert resolved["server_name"] == "web-search"
        assert resolved["tool_name"] == "brave_web_search"
        assert resolved["allowed"] is True

    def test_resolve_blocked_tool(self):
        router = self._make_router()
        resolved = router.resolve_tool("filesystem:write_file")
        assert resolved is not None
        assert resolved["allowed"] is False

    def test_resolve_invalid_name(self):
        router = self._make_router()
        assert router.resolve_tool("invalid") is None

    def test_server_without_tools(self):
        """Server without explicit tools lists server:* wildcard."""
        servers = [MCPServerConfig(name="generic", command="echo")]
        router = MCPRouter(mcp_servers=servers)
        tools = router.get_all_tools()
        assert "generic:*" in tools


class TestAgentConfigMCP:
    """Test MCP integration in AgentConfig."""

    def test_mcp_servers_in_config(self):
        config = AgentConfig(
            name="MCPAgent",
            mcp_servers=[{
                "name": "web-search",
                "command": "npx",
                "args": ["-y", "@anthropic/mcp-server-brave"],
                "tools": ["brave_web_search"],
            }],
        )
        assert len(config.mcp_servers) == 1
        assert config.mcp_servers[0]["name"] == "web-search"

    def test_tool_policy_in_config(self):
        config = AgentConfig(
            name="MCPAgent",
            tool_policy={
                "allowed_tools": ["web-search:brave_web_search"],
                "blocked_tools": ["filesystem:write_file"],
            },
        )
        assert config.tool_policy is not None
        assert "allowed_tools" in config.tool_policy

    def test_mcp_serialization_roundtrip(self):
        config = AgentConfig(
            name="MCPAgent",
            mcp_servers=[{"name": "search", "command": "npx", "args": ["-y", "mcp"]}],
            tool_policy={"allowed_tools": ["search:query"]},
        )
        d = config.to_dict()
        restored = AgentConfig.from_dict(d)
        assert len(restored.mcp_servers) == 1
        assert restored.mcp_servers[0]["name"] == "search"
        assert restored.tool_policy["allowed_tools"] == ["search:query"]

    def test_get_mcp_router(self):
        config = AgentConfig(
            name="MCPAgent",
            mcp_servers=[{
                "name": "web-search",
                "command": "npx",
                "tools": ["search"],
            }],
            tool_policy={
                "allowed_tools": ["web-search:search"],
            },
        )
        router = config.get_mcp_router()
        assert isinstance(router, MCPRouter)
        allowed = router.get_allowed_tools()
        assert "web-search:search" in allowed


# ── Integration: A2A + MCP together ───────────────────────────────────────

class TestA2AMCPIntegration:
    def test_mcp_tools_in_a2a_card(self):
        """MCP server tools should appear in A2A card capabilities."""
        config = AgentConfig(
            name="IntegratedAgent",
            description="Agent with MCP tools",
            tools_enabled=["web_search"],
            mcp_servers=[{
                "name": "brave",
                "command": "npx",
                "tools": ["brave_web_search"],
            }],
        )
        card = config.to_a2a_card(endpoint="https://agent.example.com")
        assert "web_search" in card.capabilities

    def test_full_config_roundtrip(self):
        """Full config with A2A, MCP, validation roundtrip."""
        config = AgentConfig(
            name="FullAgent",
            version="1.0.0",
            description="Full-featured agent",
            tools_enabled=["web_search"],
            mcp_servers=[{"name": "search", "command": "npx", "tools": ["query"]}],
            tool_policy={"allowed_tools": ["search:query"], "auto_approve": True},
        )
        # Serialize and deserialize
        d = config.to_dict()
        restored = AgentConfig.from_dict(d)
        # Generate A2A card
        card = restored.to_a2a_card(endpoint="https://example.com")
        assert card.name == "FullAgent"
        # Use MCP router
        router = restored.get_mcp_router()
        assert len(router.get_all_tools()) > 0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
