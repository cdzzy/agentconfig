# Changelog

All notable changes to AgentConfig are documented in this file.

## [2.1.0] - 2026-08-19

### Added

- **LLM-as-judge semantic constraints**: `LLMJudge` wraps any `(prompt) -> str` callable into a semantic rule evaluator; `semantic_judge_constraint()` builds constraints that catch paraphrases, hints, and indirect violations keyword lists miss. Fail-open on judge outages; verdict parsing tolerates markdown fences.

### Changed

- `ConstraintEngine.from_list` accepts live `Constraint` objects alongside dicts, so `judge_fn`/`check_fn` callables survive an engine rebuild inside `AgentExecutor`.
- `AgentConfig.to_dict` serializes live `Constraint` objects in `constraints`.
- JSON Schema: `semantic_judge` added to the constraint type enum.

## [2.0.0] - 2026-08-15

### Added

- **Config versioning and diffing** (`#5`): `ConfigVersionManager` with `commit`, `history`, `diff`, `structured_diff`, and `rollback` operations. Structured diffs ignore volatile auto-generated fields (`config_id`, `created_at`).
- **Config hot-reload** (`#6`): `ConfigWatcher` / `watch_config` for file-based reload, plus `RuntimeConfigStore` and `create_reload_blueprint` exposing a REST API (`PUT/GET /agents/<id>/config`, `/history`, `/rollback`) for zero-downtime updates.
- **YAML/TOML class methods** (`#2`): `AgentConfig.from_yaml`, `from_toml`, `to_yaml`, `to_toml`. `pyyaml` and `tomli-w` promoted to core dependencies.
- **JSON Schema exposure** (`#1`): `get_schema()` and `schema_file()` for IDE autocomplete and CI/CD integration. The `agentconfig validate` CLI now validates JSON, YAML, and TOML against the schema.
- **MCP env-var substitution** (`#4`): `substitute_env()` plus `MCPServerConfig.resolve_env()` / `resolve_args()` for `${VAR}` secret placeholders.
- **A2A export CLI** (`#3`): `agentconfig export-a2a` command backed by the library's `generate_a2a_card`.
- **Hot-reload CLI**: `agentconfig watch` command.

### Changed

- `agentconfig validate` now uses the JSON Schema (previously manual field checks, JSON-only).
- Fixed a broken example (`examples/healthcare_agent.toml`) and Windows console encoding in the CLI.

## [1.0.0] - initial release

- Business-semantic intent parsing, constraint enforcement, web UI, A2A/MCP support, `.agent/` portable directory support.
