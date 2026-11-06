"""
DSPy Export — turn an AgentConfig into a DSPy program skeleton.

DSPy treats prompts as programs: a ``Signature`` declares inputs/outputs, a
``Module`` wires them, and a compiler (GEPA / SIMBA / BootstrapFewShot…) tunes
the instructions and demonstrations against a metric. AgentConfig solves the
complementary half — turning business intent and constraints into a runnable
configuration.

This exporter emits the bridge: a self-contained Python file containing

- a ``dspy.Signature`` whose docstring carries the system prompt and every
  business constraint,
- a ``dspy.Module`` that uses ``ChainOfThought`` (or ``Predict``),
- a dependency-free ``check_constraints()`` that mirrors the keyword and
  length rules of :class:`~agentconfig.semantic.constraint.ConstraintEngine`,
- LM settings derived from ``ModelConfig`` (provider mapped to a LiteLLM-style
  model string),
- an optimizer template for prompt compilation.

DSPy is **not** imported by this module and is not a dependency of
agentconfig — only source text is generated.

Usage::

    from agentconfig import AgentConfig, export_dspy_program, save_dspy_program

    source = export_dspy_program(config)
    save_dspy_program(config, "support_bot_dspy.py")

    # Then, in an environment with DSPy installed:
    #   pip install dspy
    #   python support_bot_dspy.py
"""

from __future__ import annotations

import json
import pprint
import re
from pathlib import Path
from typing import Optional

from agentconfig.semantic.config_gen import AgentConfig, ModelConfig
from agentconfig.semantic.constraint import Constraint

_PROVIDER_PREFIXES = {
    "openai": "openai",
    "anthropic": "anthropic",
    "azure": "azure",
    "ollama": "ollama_chat",
    "google": "gemini",
    "gemini": "gemini",
    "groq": "groq",
    "mistral": "mistral",
}


def _class_base(name: str, config_id: str) -> str:
    """Convert a config name into a valid CamelCase Python class base."""
    tokens = re.findall(r"[A-Za-z0-9]+", name or "")
    pieces: list[str] = []
    for token in tokens:
        if token.isupper() or not any(ch.isupper() for ch in token[1:]):
            pieces.append(token[:1].upper() + token[1:].lower())
        else:
            pieces.append(token[:1].upper() + token[1:])
    base = "".join(pieces)
    if not base:
        suffix = re.sub(r"[^A-Za-z0-9]", "", config_id)[:8]
        base = f"Agent{suffix}"
    if base[0].isdigit():
        base = f"Agent{base}"
    return base


def _lm_model(model: ModelConfig) -> str:
    """Map a ModelConfig provider/model pair to a LiteLLM-style model string."""
    model_name = (model.model or "gpt-4o-mini").strip()
    prefix = _PROVIDER_PREFIXES.get((model.provider or "").strip().lower())
    if prefix and "/" not in model_name:
        return f"{prefix}/{model_name}"
    return model_name


def _normalized_constraints(config: AgentConfig) -> list[dict]:
    """Constraint dicts that can be translated into generated Python checks."""
    result: list[dict] = []
    for item in config.constraints or []:
        if isinstance(item, Constraint):
            data = item.to_dict()
        elif isinstance(item, dict):
            data = dict(item)
        else:
            continue
        if not data.get("type"):
            continue
        result.append(data)
    return result


def _instructions(config: AgentConfig, constraints: list[dict]) -> str:
    """The Signature docstring: system prompt plus hard constraints."""
    prompt = (config.system_prompt or "").strip()
    if not prompt and config.intent is not None:
        prompt = config.intent.to_system_prompt().strip()
    if not prompt:
        prompt = f"You are {config.name}."

    if constraints:
        lines = [prompt, "", "Hard constraints (never violate):"]
        for constraint in constraints:
            description = (
                constraint.get("description") or constraint.get("id") or ""
            ).strip()
            if description:
                lines.append(f"- {description}")
        prompt = "\n".join(lines)

    return prompt


def export_dspy_program(
    config: AgentConfig,
    *,
    module_name: Optional[str] = None,
    reasoning: bool = True,
    include_optimizer: bool = True,
) -> str:
    """
    Generate a DSPy program skeleton for an AgentConfig.

    Args:
        config: The compiled agent configuration to export.
        module_name: Base name for the generated Signature/Module classes
            (defaults to the config name). Sanitised to a Python identifier.
        reasoning: Use ``dspy.ChainOfThought`` (default) instead of
            ``dspy.Predict``.
        include_optimizer: Include the prompt-compilation template
            (BootstrapFewShotWithRandomSearch / GEPA / SIMBA).

    Returns:
        Python source code as a string. It compiles with ``compile()`` even in
        environments where DSPy is not installed.

    Raises:
        TypeError: If ``config`` is not an :class:`AgentConfig`.
    """
    if not isinstance(config, AgentConfig):
        raise TypeError(
            f"export_dspy_program expects an AgentConfig, got {type(config).__name__}"
        )

    base = _class_base(module_name or config.name, config.config_id)
    signature_name = f"{base}Signature"
    program_name = f"{base}Program"

    constraints = _normalized_constraints(config)
    instructions = _instructions(config, constraints)
    lm_model = _lm_model(config.model)

    metadata = {
        "config_id": config.config_id,
        "name": config.name,
        "version": config.version,
        "provider": config.model.provider,
        "model": config.model.model,
        "temperature": config.model.temperature,
        "max_tokens": config.model.max_tokens,
        "max_turns": config.max_turns,
        "tools_enabled": config.tools_enabled,
        "tools_disabled": config.tools_disabled,
    }

    lm_args: dict = {
        "model": lm_model,
        "temperature": config.model.temperature,
        "max_tokens": config.model.max_tokens,
    }
    if config.model.api_base:
        lm_args["api_base"] = config.model.api_base

    predictor = "dspy.ChainOfThought" if reasoning else "dspy.Predict"

    lines: list[str] = [
        '"""',
        f"DSPy program generated from AgentConfig {config.config_id} "
        f"({config.name} v{config.version}).",
        "",
        "Generated by agentconfig.dspy_export. This is a skeleton:",
        "- The Signature docstring carries the system prompt and constraints.",
        f"- The Module uses {predictor} for the call.",
        "- check_constraints() mirrors ConstraintEngine's keyword and length",
        "  rules; semantic-judge and callable constraints need wiring by hand.",
        "- The optimizer block at the bottom compiles the prompt against a metric.",
        "",
        "Install DSPy first: pip install dspy",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "import re",
        "from typing import Any",
        "",
        "try:",
        "    import dspy",
        "except ImportError as exc:  # pragma: no cover - environment setup",
        '    raise ImportError("This program requires DSPy: pip install dspy") from exc',
        "",
        f"CONFIG_METADATA: dict[str, Any] = {pprint.pformat(metadata, width=88, sort_dicts=False)}",
        "",
        f"LM_ARGS: dict[str, Any] = {pprint.pformat(lm_args, width=88, sort_dicts=False)}",
        "",
        f"CONSTRAINTS: list[dict[str, Any]] = {pprint.pformat(constraints, width=88, sort_dicts=False)}",
        "",
    ]

    if config.tools_enabled:
        lines.append("# Enabled tools (wire them into dspy.ReAct when you add tool functions):")
        for tool in config.tools_enabled:
            lines.append(f"# - {tool}")
        lines.append("")

    lines.extend([
        f"class {signature_name}(dspy.Signature):",
        f"    {_string_literal(instructions)}",
        "",
        '    user_input: str = dspy.InputField(desc="The user\'s message or question.")',
        "    answer: str = dspy.OutputField(",
        '        desc="The response for the user, following every constraint above."',
        "    )",
        "",
        "",
        "def check_constraints(text: str) -> list[str]:",
        '    """Return human-readable violations for a candidate response."""',
        "    violations: list[str] = []",
        "    lowered = text.lower()",
        "    for constraint in CONSTRAINTS:",
        '        ctype = constraint.get("type", "")',
        '        keywords = constraint.get("keywords") or []',
        "",
        '        if ctype in ("forbidden_keyword", "forbidden_topic"):',
        "            for keyword in keywords:",
        "                if keyword.lower() in lowered:",
        '                    violations.append(f"{constraint[\'id\']}: forbidden content \'{keyword}\'")',
        '        elif ctype == "required_keyword":',
        "            if keywords and not any(k.lower() in lowered for k in keywords):",
        '                violations.append(f"{constraint[\'id\']}: no required keyword present")',
        '        elif ctype == "max_length":',
        '            limit = constraint.get("max_chars") or 0',
        "            if limit and len(text) > limit:",
        '                violations.append(f"{constraint[\'id\']}: exceeds {limit} chars")',
        '        elif ctype == "min_length":',
        '            limit = constraint.get("min_chars") or 0',
        "            if limit and len(text.strip()) < limit:",
        '                violations.append(f"{constraint[\'id\']}: shorter than {limit} chars")',
        '        elif ctype == "escalation":',
        "            for keyword in keywords:",
        "                if keyword.lower() in lowered:",
        '                    violations.append(f"{constraint[\'id\']}: escalation trigger \'{keyword}\'")',
        '        elif ctype == "tone_check":',
        "            if keywords and not any(k.lower() in lowered for k in keywords):",
        '                violations.append(f"{constraint[\'id\']}: tone check failed")',
        '        elif ctype == "custom":',
        '            pattern = constraint.get("pattern") or ""',
        "            if pattern and re.search(pattern, text, re.IGNORECASE):",
        '                violations.append(f"{constraint[\'id\']}: custom pattern matched")',
        "        # semantic_judge constraints need an LLM judge; wire them by hand.",
        "    return violations",
        "",
        "",
        f"class {program_name}(dspy.Module):",
        f'    """DSPy program for {config.name}."""',
        "",
        "    def __init__(self) -> None:",
        "        super().__init__()",
        f"        self.generate = {predictor}({signature_name})",
        "",
        "    def forward(self, user_input: str):",
        '        """Run the program and attach constraint violations to the prediction."""',
        "        prediction = self.generate(user_input=user_input)",
        '        prediction["violations"] = check_constraints(prediction["answer"])',
        "        return prediction",
        "",
        "",
        f"def build_program() -> {program_name}:",
        '    """Construct the program and configure DSPy\'s default LM."""',
        "    dspy.configure(lm=dspy.LM(**LM_ARGS))",
        f"    return {program_name}()",
        "",
        "",
        'if __name__ == "__main__":  # pragma: no cover - manual smoke test',
        "    program = build_program()",
        '    prediction = program.forward("Hello!")',
        '    print(prediction["answer"])',
        '    print("violations:", prediction["violations"])',
    ])

    if include_optimizer:
        lines.extend([
            "",
            "",
            "# ── Compile the prompt instead of hand-writing it ─────────────────────",
            "# DSPy optimizers tune the Signature instructions and few-shot demos",
            "# against a metric. Provide a metric and a training set, then pick one:",
            "#",
            "# from dspy.teleprompt import BootstrapFewShotWithRandomSearch, GEPA",
            "#",
            "# compiled = BootstrapFewShotWithRandomSearch(",
            "#     metric=your_metric, max_bootstrapped_demos=4, max_labeled_demos=4,",
            "# ).compile(build_program(), trainset=trainset)",
            "#",
            "# compiled = GEPA(metric=your_metric, auto=\"light\").compile(",
            "#     build_program(), trainset=trainset,",
            "# )",
            "#",
            "# SIMBA works the same way: dspy.SIMBA(metric=your_metric).compile(...)",
            f"# compiled.save(\"{base.lower()}_compiled.json\")",
        ])

    return "\n".join(lines) + "\n"


def save_dspy_program(
    config: AgentConfig,
    path: str,
    *,
    module_name: Optional[str] = None,
    reasoning: bool = True,
    include_optimizer: bool = True,
) -> str:
    """
    Write a generated DSPy program to ``path`` and return the path.

    Parent directories are created when missing.
    """
    source = export_dspy_program(
        config,
        module_name=module_name,
        reasoning=reasoning,
        include_optimizer=include_optimizer,
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return str(target)


def _string_literal(value: str) -> str:
    """A valid Python string literal on one line, for the Signature docstring."""
    return json.dumps(value, ensure_ascii=False)
