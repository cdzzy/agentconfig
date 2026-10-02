# Changelog

All notable changes to AgentConfig are documented in this file.

## [2.4.1] - 2026-10-02

### Fixed

- **JSON Schema `pattern` semantics** (`agentconfig.validation.validator`): the built-in walker used `re.match`, which only anchors at the start of the string; the JSON Schema spec defines `pattern` as an *unanchored* substring match, so schemas with non-anchored patterns (e.g. `"abc"` should match `"xabc"`) now validate correctly and agree with the strict (pydantic) path.
- **PREFERENCES.md duplicate keys** (`agentconfig.portable`): keys that normalize to the same value (e.g. `Preferred Name` vs `preferred_name`) previously overwrote each other silently; the parser now raises a clear `ValueError`.
- **Atomic file writes** (`agentconfig.portable`): `LESSONS.md` and `PREFERENCES.md` are written via a temp-file + rename, so a crash mid-write can no longer leave a truncated file.

### Changed

- The bundled JSON Schema is loaded once and cached (schema is read-only); `get_schema()` returns a defensive copy.
- `validate_dict` / `validate_config` `mode` parameters now carry a precise `Optional[Union[str, "Strictness"]]` annotation instead of `Optional[Any]`.
- Release workflow: PyPI publish tolerates re-pushes of the same tag (`skip-existing: true`) and a `concurrency` group serializes overlapping releases.

## [2.4.0] - 2026-10-02

### Added

- **Strict validation mode** (`agentconfig.validation.strict`): optional
  [Pydantic](https://docs.pydantic.dev/) v2 models selected via
  `validate_dict(data, mode="strict")`, `validate_config(path, mode=...)`,
  or the `Strictness` enum. Pydantic is a new optional extra:
  `pip install "cdzzy-agentconfig[strict]"`.
  - `ConfigDict(strict=True, extra="forbid")` throughout — no silent type
    coercion (`"20"` never passes as an integer) and unknown fields are
    rejected, so schema drift fails loud instead of slipping through.
  - All violations are reported in one pass with precise locations, where
    the built-in walker stops at the first type mismatch in a subtree.
  - `ValidationResult` extended with `mode`, `notes`, and `model` — on
    strict success, `result.model` is a typed `AgentConfigModel` you can
    access attribute-style and `model_dump()` back to a plain dict.
  - 6 strict models mirror the JSON Schema (AgentIntent / ModelConfig /
    Constraint / MCPServerConfig / ToolPolicy / AgentConfig); JSON Schema
    `"number"` fields accept both ints and floats via a `Union` type, so
    `temperature: 1` stays valid.
  - Graceful fallback: without pydantic installed, strict-mode requests
    fall back to the built-in validator and the result carries an
    explanatory note in `result.notes` — pipelines never hard-fail on an
    optional extra.
  - `normalize_mode()` coerces `None` / `"lenient"` / `"strict"` /
    `Strictness` members; unknown values raise `ValueError`.

### Changed

- `pydantic>=2.5` added to the `dev` extra so CI always covers the strict
  validation path.
- `ValidationResult.__str__` now appends a `Notes:` block when notes are
  present; output is unchanged otherwise.

## [2.3.1] - 2026-09-25

### Changed

- CI: pip dependency cache added to the lint and test jobs for faster, more reliable installs.

## [2.3.0] - 2026-09-20

### Added

- **Markdown gateway** (`agentconfig.gateway`): treat SKILL.md and AGENTS.md as first-class agent configuration. `parse_skill_md` / `render_skill_md` / `parse_agents_md` / `render_agents_md` round-trip through a shared `ConfigTree` IR with strict YAML-frontmatter validation and actionable errors (`GatewayParseError` / `GatewayValidationError`); tree-level round-trips are lossless.
- **CLI**: `agentconfig skill import` (SKILL.md → config JSON) and `agentconfig skill export` (config JSON → SKILL.md or AGENTS.md).
- **Release automation** (`.github/workflows/release.yml`): PyPI publish on `v*` tags, refused when the tag doesn't match `__version__`.

### Changed

- `requires-python` aligned to >=3.9 to match the CI test matrix (3.9–3.13, fail-fast off) and the new ruff lint job.

## [2.2.0] - 2026-08-27

### Added

- **Framework adapter plugins** (`agentconfig.adapters`): constraint-enforcing wrappers for LangGraph (`wrap_langgraph_node`), AutoGen (`wrap_autogen_reply`), and CrewAI (`wrap_crewai_agent`). Dependency-free — wrappers work with duck-typed callables following each framework's calling convention, so blocked responses are replaced by the configured fallback before reaching the user.

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
