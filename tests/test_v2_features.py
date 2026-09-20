"""
Tests for new v2.0.0 features:
- AgentConfig.from_yaml/from_toml/to_yaml/to_toml (Issue #2)
- MCP env var substitution (Issue #4)
- Config versioning and diffing (Issue #5)
- Hot-reload watcher and runtime store (Issue #6)
"""

import os
import time

import pytest

from agentconfig.hotreload import (
    ConfigWatcher,
    RuntimeConfigStore,
    create_reload_blueprint,
    watch_config,
)
from agentconfig.mcp import MCPRouter, MCPServerConfig, ToolPolicy, substitute_env
from agentconfig.semantic.config_gen import AgentConfig
from agentconfig.validation import get_schema, schema_file
from agentconfig.versioning import (
    ConfigVersionManager,
    diff_configs,
    diff_dicts,
)

# ── YAML/TOML serialization (Issue #2) ────────────────────────────────────

class TestYAMLToml:

    def test_from_yaml(self):
        yaml_str = "name: SupportAgent\nmax_turns: 30\n"
        config = AgentConfig.from_yaml(yaml_str)
        assert config.name == "SupportAgent"
        assert config.max_turns == 30

    def test_from_toml(self):
        toml_str = 'name = "SupportAgent"\nmax_turns = 30\n'
        config = AgentConfig.from_toml(toml_str)
        assert config.name == "SupportAgent"
        assert config.max_turns == 30

    def test_to_yaml_roundtrip(self):
        config = AgentConfig(name="Roundtrip", max_turns=42)
        restored = AgentConfig.from_yaml(config.to_yaml())
        assert restored.name == "Roundtrip"
        assert restored.max_turns == 42

    def test_to_toml_roundtrip(self):
        config = AgentConfig(name="Roundtrip", max_turns=42)
        restored = AgentConfig.from_toml(config.to_toml())
        assert restored.name == "Roundtrip"
        assert restored.max_turns == 42

    def test_from_yaml_non_mapping_raises(self):
        with pytest.raises(ValueError):
            AgentConfig.from_yaml("- just\n- a list\n")


# ── MCP env var substitution (Issue #4) ───────────────────────────────────

class TestMCPEnv:

    def test_substitute_env_basic(self):
        env = {"API_KEY": "sk-123"}
        assert substitute_env("Bearer ${API_KEY}", env) == "Bearer sk-123"

    def test_substitute_env_unknown_left_intact(self):
        assert substitute_env("${MISSING}", {}) == "${MISSING}"

    def test_substitute_env_uses_os_environ(self):
        os.environ["AGENTCONFIG_TEST_VAR"] = "hello"
        try:
            assert substitute_env("${AGENTCONFIG_TEST_VAR}") == "hello"
        finally:
            del os.environ["AGENTCONFIG_TEST_VAR"]

    def test_mcp_server_resolve_env(self):
        server = MCPServerConfig(
            name="web-search",
            command="npx",
            env={"BRAVE_API_KEY": "${BRAVE_API_KEY}"},
            args=["--token", "${TOKEN}"],
        )
        env = {"BRAVE_API_KEY": "sk-brave", "TOKEN": "tok-1"}
        resolved = server.resolve_env(env)
        assert resolved["BRAVE_API_KEY"] == "sk-brave"
        assert server.resolve_args(env) == ["--token", "tok-1"]

    def test_mcp_router_with_env(self):
        server = MCPServerConfig(
            name="filesystem",
            command="npx",
            args=["-y", "@anthropic/mcp-server-filesystem", "/data"],
            tools=["read_file", "write_file"],
        )
        policy = ToolPolicy(allowed_tools=["filesystem:read_file"], blocked_tools=["filesystem:write_file"])
        router = MCPRouter(mcp_servers=[server], tool_policy=policy)
        assert "filesystem:read_file" in router.get_allowed_tools()
        assert "filesystem:write_file" in router.get_blocked_tools()


# ── Versioning (Issue #5) ─────────────────────────────────────────────────

class TestVersioning:

    def test_commit_and_history(self):
        manager = ConfigVersionManager()
        c1 = AgentConfig(name="Agent", max_turns=20)
        c2 = AgentConfig(name="Agent", max_turns=30)
        v1 = manager.commit(c1, "Initial")
        manager.commit(c2, "Bumped turns")
        assert [v.id for v in manager.history()] == ["v1", "v2"]
        assert v1.message == "Initial"
        assert manager.current.id == "v2"

    def test_rollback(self):
        manager = ConfigVersionManager()
        manager.commit(AgentConfig(name="Agent", max_turns=20), "Initial")
        manager.commit(AgentConfig(name="Agent", max_turns=30), "Bumped")
        restored = manager.rollback("v1")
        assert restored.max_turns == 20

    def test_rollback_unknown_raises(self):
        manager = ConfigVersionManager()
        manager.commit(AgentConfig(name="Agent"), "Initial")
        with pytest.raises(ValueError):
            manager.rollback("v99")

    def test_diff(self):
        manager = ConfigVersionManager()
        manager.commit(AgentConfig(name="Agent", max_turns=20), "Initial")
        manager.commit(AgentConfig(name="Agent", max_turns=30), "Bumped")
        diff = manager.diff("v1", "v2")
        assert "max_turns" in diff
        assert "-" in diff and "+" in diff

    def test_diff_identical_is_empty(self):
        manager = ConfigVersionManager()
        manager.commit(AgentConfig(name="Agent"), "Initial")
        manager.commit(AgentConfig(name="Agent"), "Same")
        assert manager.diff("v1", "v2") == ""

    def test_structured_diff(self):
        manager = ConfigVersionManager()
        manager.commit(AgentConfig(name="Agent", max_turns=20), "Initial")
        manager.commit(AgentConfig(name="Agent", max_turns=30, description="hi"), "Change")
        d = manager.structured_diff("v1", "v2")
        assert "max_turns" in d["changed"]
        assert "description" in d["changed"]

    def test_diff_dicts(self):
        d = diff_dicts({"a": 1, "b": 2}, {"b": 3, "c": 4})
        assert d["added"] == {"c": 4}
        assert d["removed"] == {"a": 1}
        assert d["changed"] == {"b": {"from": 2, "to": 3}}

    def test_diff_configs_text(self):
        out = diff_configs({"name": "A"}, {"name": "B"})
        assert "A" in out and "B" in out


# ── Hot-reload (Issue #6) ─────────────────────────────────────────────────

class TestConfigWatcher:

    def test_manual_reload_detects_change(self, tmp_path):
        config_file = tmp_path / "agent.json"
        AgentConfig(name="Agent", max_turns=10).save(str(config_file))

        seen = []
        watcher = ConfigWatcher(str(config_file), on_change=lambda c: seen.append(c))
        assert watcher.reload() is None  # no change yet

        # Modify the file, then reload
        time.sleep(0.05)
        AgentConfig(name="Agent", max_turns=99).save(str(config_file))
        loaded = watcher.reload()
        assert loaded is not None
        assert loaded.max_turns == 99
        assert len(seen) == 1

    def test_watch_background_thread(self, tmp_path):
        config_file = tmp_path / "agent.json"
        AgentConfig(name="Agent", max_turns=10).save(str(config_file))

        seen = []
        watcher = watch_config(str(config_file), on_change=lambda c: seen.append(c), poll_interval=0.1)
        watcher.start()
        try:
            # Modify the file
            time.sleep(0.2)
            AgentConfig(name="Agent", max_turns=20).save(str(config_file))
            deadline = time.time() + 3
            while not seen and time.time() < deadline:
                time.sleep(0.1)
            assert len(seen) >= 1
            assert seen[-1].max_turns == 20
        finally:
            watcher.stop()

    def test_context_manager(self, tmp_path):
        config_file = tmp_path / "agent.json"
        AgentConfig(name="Agent").save(str(config_file))
        with watch_config(str(config_file)) as watcher:
            assert watcher._thread.is_alive()
        assert watcher._thread is None


class TestRuntimeConfigStore:

    def _store(self):
        store = RuntimeConfigStore()
        store.register("agent-1", AgentConfig(name="Agent", max_turns=20))
        return store

    def test_register_and_get(self):
        store = self._store()
        assert store.get("agent-1").max_turns == 20

    def test_update_merge(self):
        store = self._store()
        updated = store.update("agent-1", {"max_turns": 50}, message="bump")
        assert updated.max_turns == 50
        assert len(store.history("agent-1")) == 2

    def test_update_unknown_raises(self):
        store = self._store()
        with pytest.raises(KeyError):
            store.update("nope", {"max_turns": 1})

    def test_rollback(self):
        store = self._store()
        store.update("agent-1", {"max_turns": 50})
        rolled = store.rollback("agent-1", "v1")
        assert rolled.max_turns == 20

    def test_agents_list(self):
        store = self._store()
        store.register("agent-2", AgentConfig(name="Other"))
        assert store.agents() == ["agent-1", "agent-2"]

    def test_diff(self):
        store = self._store()
        store.update("agent-1", {"max_turns": 50})
        diff = store.diff("agent-1", "v1", "v2")
        assert "max_turns" in diff


class TestReloadBlueprint:

    def test_rest_api(self):
        try:
            from flask import Flask
        except ImportError:
            pytest.skip("flask not installed")

        store = RuntimeConfigStore()
        store.register("agent-1", AgentConfig(name="Agent", max_turns=20))

        app = Flask(__name__)
        app.register_blueprint(create_reload_blueprint(store), url_prefix="/api")
        client = app.test_client()

        # GET config
        resp = client.get("/api/agents/agent-1/config")
        assert resp.status_code == 200
        assert resp.get_json()["max_turns"] == 20

        # PUT config (update)
        resp = client.put("/api/agents/agent-1/config", json={"max_turns": 99})
        assert resp.status_code == 200
        assert resp.get_json()["max_turns"] == 99

        # GET history
        resp = client.get("/api/agents/agent-1/history")
        assert resp.status_code == 200
        assert len(resp.get_json()["history"]) == 2

        # POST rollback
        resp = client.post("/api/agents/agent-1/rollback", json={"version": "v1"})
        assert resp.status_code == 200
        assert resp.get_json()["max_turns"] == 20

        # List agents
        resp = client.get("/api/agents")
        assert resp.status_code == 200
        assert resp.get_json()["agents"] == ["agent-1"]

        # Unknown agent
        assert client.get("/api/agents/nope/config").status_code == 404


# ── Schema exposure (Issue #1) ────────────────────────────────────────────

class TestSchemaExposure:

    def test_get_schema(self):
        schema = get_schema()
        assert schema["title"] == "AgentConfig"
        assert "properties" in schema

    def test_schema_file_exists(self):
        import os
        assert os.path.isfile(schema_file())
