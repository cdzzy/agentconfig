"""
Tests for organization / team layered configuration sharing.

Covers the three merge rules that make shared configs safe (constraint
inheritance by id, disabled-tool union, enabled-tool narrowing), layer
precedence, file/directory loading, provenance reporting, and validation of
the resolved config.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from agentconfig.org import (
    LAYER_LEVELS,
    ConfigLayer,
    LayeredConfigResolver,
    deep_merge,
    merge_config_data,
    merge_constraints,
)

ORG = {
    "name": "support-agent",
    "system_prompt": "You are a support agent.",
    "model": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.7},
    "constraints": [
        {"id": "no_pii", "type": "forbidden_keyword", "description": "Never expose PII"},
        {"id": "no_pricing", "type": "forbidden_topic", "description": "Never discuss pricing"},
    ],
    "tools_enabled": ["search", "database", "shell"],
    "tools_disabled": ["shell"],
    "max_turns": 10,
}

TEAM = {
    "model": {"temperature": 0.3},
    "description": "Customer success team defaults",
    "tools_enabled": ["search", "database"],
    "metadata": {"team": "customer-success"},
}

AGENT = {
    "name": "billing-agent",
    "system_prompt": "You are a billing specialist.",
    "tools_enabled": ["search", "database", "shell"],
    "constraints": [
        {"id": "no_pii", "type": "forbidden_keyword", "description": "Never expose PII (tightened)"},
    ],
}


class TestLayerValidation:
    def test_accepts_known_levels(self):
        for level in LAYER_LEVELS:
            assert ConfigLayer(name="x", level=level).level == level

    def test_rejects_unknown_level(self):
        with pytest.raises(ValueError, match="Unknown layer level"):
            ConfigLayer(name="x", level="global")

    def test_levels_are_ordered(self):
        assert LAYER_LEVELS == ("organization", "team", "agent")


class TestDeepMerge:
    def test_scalar_override_wins(self):
        assert deep_merge({"a": 1}, {"a": 2}) == {"a": 2}

    def test_nested_dicts_merge(self):
        merged = deep_merge({"m": {"x": 1, "y": 2}}, {"m": {"y": 3, "z": 4}})
        assert merged == {"m": {"x": 1, "y": 3, "z": 4}}

    def test_lists_are_replaced(self):
        assert deep_merge({"l": [1, 2]}, {"l": [3]}) == {"l": [3]}

    def test_inputs_not_mutated(self):
        base = {"m": {"x": 1}}
        override = {"m": {"y": 2}}
        deep_merge(base, override)
        assert base == {"m": {"x": 1}}
        assert override == {"m": {"y": 2}}


class TestConstraintMerging:
    def test_parent_constraints_are_inherited(self):
        merged = merge_constraints(
            [{"id": "a", "description": "parent"}],
            [{"id": "b", "description": "child"}],
        )
        assert [c["id"] for c in merged] == ["a", "b"]

    def test_child_overrides_same_id(self):
        merged = merge_constraints(
            [{"id": "a", "description": "parent"}],
            [{"id": "a", "description": "child"}],
        )
        assert len(merged) == 1
        assert merged[0]["description"] == "child"

    def test_child_cannot_drop_parent_constraint(self):
        # The core inheritance guarantee: omitting a guardrail in the child
        # layer must not remove it from the effective config.
        merged = merge_config_data(ORG, AGENT)
        ids = [c["id"] for c in merged["constraints"]]
        assert "no_pii" in ids
        assert "no_pricing" in ids  # not mentioned by the agent, still present


class TestRestrictiveToolPolicy:
    def test_disabled_tools_union(self):
        # A child listing a tool as enabled must not re-enable a parent block.
        merged = merge_config_data(ORG, {"tools_enabled": ["shell"]})
        assert "shell" in merged["tools_disabled"]

    def test_enabled_tools_intersect_with_parent_allowlist(self):
        merged = merge_config_data(ORG, AGENT)
        # Parent allowlist is {search, database, shell}; child asks for the
        # same set; the union rule already blocks shell, and the allowlist
        # intersection keeps the surface at the parent's declared set.
        assert merged["tools_enabled"] == ["database", "search", "shell"]

    def test_child_cannot_widen_allowlist(self):
        base = {"tools_enabled": ["search", "database"]}
        child = {"tools_enabled": ["search", "database", "shell"]}
        merged = merge_config_data(base, child)
        assert "shell" not in merged["tools_enabled"]

    def test_child_narrows_allowlist(self):
        base = {"tools_enabled": ["search", "database", "files"]}
        child = {"tools_enabled": ["search"]}
        merged = merge_config_data(base, child)
        assert merged["tools_enabled"] == ["search"]

    def test_parent_allowlist_applies_when_child_silent(self):
        base = {"tools_enabled": ["search", "database"]}
        merged = merge_config_data(base, {"max_turns": 5})
        assert merged["tools_enabled"] == ["database", "search"]

    def test_child_allowlist_used_when_parent_silent(self):
        merged = merge_config_data({"max_turns": 5}, {"tools_enabled": ["search"]})
        assert merged["tools_enabled"] == ["search"]


class TestResolverPrecedence:
    def test_later_layer_wins_for_scalars(self):
        resolver = (
            LayeredConfigResolver()
            .add_dict(ORG, "organization")
            .add_dict(TEAM, "team")
            .add_dict(AGENT, "agent")
        )
        resolved = resolver.resolve()
        assert resolved["name"] == "billing-agent"
        assert resolved["system_prompt"] == "You are a billing specialist."
        assert resolved["model"]["temperature"] == 0.3

    def test_nested_fields_merge_across_layers(self):
        resolved = LayeredConfigResolver().add_dict(ORG, "organization").add_dict(
            TEAM, "team"
        ).resolve()
        assert resolved["model"] == {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.3}

    def test_same_level_last_wins(self):
        resolver = (
            LayeredConfigResolver()
            .add_dict({"max_turns": 5}, "team", name="first")
            .add_dict({"max_turns": 7}, "team", name="second")
        )
        assert resolver.resolve()["max_turns"] == 7

    def test_level_order_ignores_insertion_order(self):
        resolver = (
            LayeredConfigResolver()
            .add_dict(AGENT, "agent")          # added first...
            .add_dict(ORG, "organization")     # ...but must still lose
        )
        assert resolver.resolve()["name"] == "billing-agent"

    def test_empty_resolver_resolves_to_empty_dict(self):
        assert LayeredConfigResolver().resolve() == {}

    def test_resolve_config_raises_when_empty(self):
        with pytest.raises(ValueError, match="No configuration layers"):
            LayeredConfigResolver().resolve_config()


class TestResolveToAgentConfig:
    def test_produces_valid_agent_config(self):
        resolver = (
            LayeredConfigResolver()
            .add_dict(ORG, "organization")
            .add_dict(TEAM, "team")
            .add_dict(AGENT, "agent")
        )
        config = resolver.resolve_config()

        from agentconfig.semantic.config_gen import AgentConfig

        assert isinstance(config, AgentConfig)
        assert config.name == "billing-agent"
        assert config.model.temperature == 0.3
        constraint_ids = [c["id"] for c in config.constraints]
        assert "no_pii" in constraint_ids
        assert "no_pricing" in constraint_ids

    def test_invalid_merge_raises_with_reasons(self):
        resolver = LayeredConfigResolver().add_dict({"name": 123}, "organization")
        with pytest.raises(ValueError, match="failed validation"):
            resolver.resolve_config()


class TestExplain:
    def test_reports_source_and_value_per_field(self):
        resolver = (
            LayeredConfigResolver()
            .add_dict(ORG, "organization")
            .add_dict(TEAM, "team")
            .add_dict(AGENT, "agent")
        )
        explained = resolver.explain()

        assert explained["name"]["source"] == "agent"
        assert explained["name"]["value"] == "billing-agent"
        # temperature is defined by org and team → team is the winner
        assert explained["model"]["source"] == "team"
        assert "organization" in explained["model"]["layers"]

    def test_lists_every_contributing_layer(self):
        resolver = (
            LayeredConfigResolver()
            .add_dict({"max_turns": 5}, "organization")
            .add_dict({"max_turns": 10}, "team")
        )
        entry = resolver.explain()["max_turns"]
        assert entry["layers"] == ["organization", "team"]
        assert entry["source"] == "team"
        assert entry["value"] == 10


class TestFileLoading:
    def test_add_file_loads_yaml(self, tmp_path):
        import yaml

        path = tmp_path / "org.yaml"
        path.write_text(yaml.safe_dump(ORG), encoding="utf-8")

        resolver = LayeredConfigResolver().add_file(str(path), "organization")
        resolved = resolver.resolve()
        assert resolved["max_turns"] == 10
        assert resolved["name"] == "support-agent"

    def test_add_file_loads_json(self, tmp_path):
        import json

        path = tmp_path / "agent.json"
        path.write_text(json.dumps(AGENT), encoding="utf-8")

        resolver = LayeredConfigResolver().add_file(str(path), "agent")
        assert resolver.resolve()["name"] == "billing-agent"

    def test_from_directory_loads_all_present_layers(self, tmp_path):
        import yaml

        (tmp_path / "organization.yaml").write_text(yaml.safe_dump(ORG), encoding="utf-8")
        (tmp_path / "team.yaml").write_text(yaml.safe_dump(TEAM), encoding="utf-8")
        # agent.yaml deliberately absent — a deployment may use only what it needs

        resolver = LayeredConfigResolver.from_directory(str(tmp_path))
        resolved = resolver.resolve()
        assert resolved["name"] == "support-agent"
        assert resolved["model"]["temperature"] == 0.3
        assert [layer.level for layer in resolver.layers()] == ["organization", "team"]

    def test_from_directory_with_custom_filenames(self, tmp_path):
        import json

        (tmp_path / "shared.json").write_text(json.dumps({"max_turns": 3}), encoding="utf-8")

        resolver = LayeredConfigResolver.from_directory(
            str(tmp_path), filenames={"team": "shared.json"}
        )
        assert resolver.resolve()["max_turns"] == 3


class TestConfigLayerConstruction:
    def test_from_dict_defaults_name_to_config_name(self):
        layer = ConfigLayer.from_dict({"name": "acme"}, "organization")
        assert layer.name == "acme"

    def test_from_dict_falls_back_to_level_for_name(self):
        layer = ConfigLayer.from_dict({"max_turns": 1}, "team")
        assert layer.name == "team"

    def test_from_config_serializes_via_to_dict(self):
        from agentconfig.semantic.config_gen import AgentConfig

        config = AgentConfig(name="from-config", max_turns=4)
        layer = ConfigLayer.from_config(config, "agent")
        assert layer.data["name"] == "from-config"
        assert layer.data["max_turns"] == 4
