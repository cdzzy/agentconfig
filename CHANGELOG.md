# Changelog

All notable changes to AgentConfig are documented in this file.

## [Unreleased]

### Changed

- **CI hardening**: upgrade all pinned GitHub Actions to current major
  releases — `actions/checkout` v4→v7, `actions/setup-python` v5→v7,
  `actions/upload-artifact` / `actions/download-artifact` v4→v7. The older
  tags run on Node 20 runners that reached end-of-life and carry known
  advisories; the new majors keep the workflows maintainable and secure.
  No package behavior change.

## [2.7.0] - 2026-11-06

### Added

- **DSPy export** (`agentconfig/dspy_export.py`): bridges AgentConfig's
  "business intent → configuration" pipeline to DSPy's
  "prompt → optimizable program" pipeline. DSPy is not a dependency — only
  source text is generated.
  - `export_dspy_program(config)` returns a self-contained Python module:
    - a `dspy.Signature` subclass whose docstring carries the system prompt
      (or the prompt generated from the intent) plus every constraint
      description;
    - a `dspy.Module` subclass using `ChainOfThought` by default
      (`reasoning=False` emits `Predict`);
    - `LM_ARGS` derived from `ModelConfig`, mapping providers to LiteLLM-style
      model strings (`openai/…`, `anthropic/…`, `azure/…`, `ollama_chat/…`,
      `gemini/…`, …) and passing `temperature`, `max_tokens`, and `api_base`;
    - `check_constraints()` — a dependency-free mirror of `ConstraintEngine`
      for forbidden keyword/topic, required keyword, min/max length,
      escalation, tone, and custom-regex rules; `semantic_judge` constraints
      are documented as requiring manual wiring;
    - `build_program()` that configures `dspy.LM(**LM_ARGS)` and constructs
      the module;
    - an optimizer template for `BootstrapFewShotWithRandomSearch`, `GEPA`
      and `SIMBA` (optional).
  - `save_dspy_program(config, path)` writes the generated module and creates
    parent directories.
  - Class names are derived from the config name (or `module_name`),
    sanitised to valid CamelCase identifiers; non-ASCII names fall back to
    `Agent<config_id>`.
  - Exported from the package root (`export_dspy_program`,
    `save_dspy_program`).

### Changed

- README gained an "Exporting to DSPy" section and a roadmap entry.

### Testing

- 23 new tests (`tests/test_dspy_export.py`): source compiles, class
  naming/sanitisation, prompt and constraint embedding, intent fallback,
  Predict/ChainOfThought toggle, optimizer inclusion, tools comments,
  provider→model mapping (OpenAI/Anthropic/Ollama/unknown/prefixed), metadata,
  empty constraints, file writing, and runtime execution against a fake
  `dspy` module (program forward pass, constraint mirror, semantic-judge
  no-op).

## [2.6.0] - 2026-11-01

### Added

- **Organization / team configuration sharing** (`agentconfig.org`): deployments
  rarely configure every agent from scratch — policy is decided at the org
  level, refined per team, then specialized per agent. This module composes
  those layers into one effective config.
  - `LayeredConfigResolver` — `add_dict` / `add_config` / `add_file` /
    `from_directory("configs/")`, with precedence
    `organization` → `team` → `agent`. Layer order is applied by level, so
    insertion order never lets a low layer win.
  - `resolve()` returns the merged dict; `resolve_config()` validates it
    against the JSON Schema and returns an `AgentConfig`.
  - `explain()` reports, per top-level field, which layers defined it and
    which one won — "where did this value come from?" without diffing files.
  - `ConfigLayer` — build a layer from a dict, an `AgentConfig`, or a
    JSON/YAML/TOML file.
- **Monotonic restriction merge rules** (`merge_config_data`): a lower layer
  can tighten a parent's policy but never loosen it.
  - `constraints` merge **by `id`** instead of replacing, so an agent cannot
    silently drop an organization-wide guardrail by omitting it (same `id`
    from the child wins, keeping the audit trail intact).
  - `tools_disabled` takes the **union**, so a child cannot re-enable a tool
    the parent blocked.
  - `tools_enabled` **intersects** with the parent's allowlist when the
    parent declares one, so a child can only narrow the tool surface.
  - `deep_merge()` and `merge_constraints()` are exported for direct use.
- **`load_raw_dict(path, format=None)`** (`agentconfig.loader`) — reads a
  config file as a plain dict without applying `AgentConfig` defaults. Needed
  by the layer loader: going through `AgentConfig` backfills
  `name='My Agent'`, `max_turns=20`, model defaults, and a sparse team layer
  would then overwrite the organization's real values.

### Changed

- **Minimum supported Python is now 3.10** (`requires-python = ">=3.10"`).
  Python 3.9 reached end-of-life on 2025-10-31 and GitHub's
  `actions/python-versions` no longer publishes 3.9 builds, so the CI matrix's
  3.9 `setup-python` step fails to provision an interpreter. The 3.9
  classifier was dropped; the CI matrix is now 3.10 / 3.11 / 3.12 / 3.13.

### Testing

- 33 new tests (`tests/test_org_layers.py`): layer validation, deep merge,
  constraint inheritance by id, the three restrictive tool-policy rules,
  precedence across levels and within a level, file and directory loading,
  `resolve_config()` validation, and provenance reporting.
- Full suite: **344 passed**; `ruff check .` and `mypy agentconfig` clean.

## [2.5.1] - 2026-10-23

### Fixed

- **`agentconfig generate` crashed while printing the generated config**
  (`agentconfig.cli.main`): `AgentConfig.constraints` holds serialized dicts
  (see `semantic/config_gen.py`), but the CLI accessed each entry with
  attribute syntax (`c.type.value` / `c.action.value`), raising `AttributeError`
  at runtime. The output block now indexes the dicts directly.
- **`_configure_utf8_output()` robustness** (`agentconfig.cli.main`):
  `reconfigure` only exists on `io.TextIOWrapper`, not the base `TextIO` type;
  the helper now probes for the attribute instead of calling it blindly.

### Changed

- **mypy now runs in CI** (`.github/workflows/ci.yml`): the type checker was
  configured in `pyproject.toml` but never executed. The lint job now installs
  mypy and checks the `agentconfig` package. The new `[tool.mypy]` block uses
  `python_version = "3.10"` (the mypy 2.x floor; 3.9 runtime compat is kept via
  `from __future__ import annotations`) with `ignore_missing_imports = true`,
  and the Python<3.11 `import tomli as tomllib` compatibility alias is
  annotated `# type: ignore[no-redef]` so the union import idiom type-checks.
- **CI concurrency guard & least privilege** (`.github/workflows/ci.yml`):
  push/PR runs now cancel stale in-progress runs for the same ref and the
  workflow only requests `contents: read`.
- **Release workflow now verifies before publishing**
  (`.github/workflows/release.yml`): the tag must match the version declared
  in `pyproject.toml`, and `ruff check .` plus `pytest tests/` run before the
  sdist/wheel build — previously the tag-push pipeline only built and pushed,
  so a mis-tagged or failing test could ship to PyPI. Version source is
  synced: `pyproject.toml` now carries 2.5.1 (the CHANGELOG was already
  updated for it).

## [2.5.0] - 2026-10-16

### Added

- **`agentconfig --version` CLI flag** (`agentconfig.cli.main`): prints the
  package version and exits 0 — previously the CLI had no way to report its
  own version.

### Fixed

- **Version drift between `__version__` and `pyproject.toml`**:
  `agentconfig.__version__` was a hard-coded literal that silently drifted
  from the declared package version (e.g. `2.4.0` vs `2.4.1`). It is now
  derived from `pyproject.toml` (single source of truth) in source
  checkouts / editable installs, falling back to `importlib.metadata` for
  regular installed copies — so the two can never disagree again.
- **CLI version source**: `_package_version()` now reuses the canonical
  `agentconfig.__version__` instead of duplicating metadata/pyproject
  lookups that could disagree.

### Added tests

- `tests/test_cli_version.py`: `--version` flag output, and a regression
  guard asserting `agentconfig.__version__ == pyproject.toml` version.

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
