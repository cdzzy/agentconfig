"""
Config Loader — Load AgentConfig from multiple file formats.

Supports JSON, YAML, and TOML configuration files with automatic
format detection based on file extension.

Usage::

    from agentconfig.loader import load_config

    # Auto-detect format from extension
    config = load_config("my_agent.yaml")

    # Explicit format
    config = load_config("agent.toml", format="toml")

    # Save to different format
    from agentconfig.loader import save_config
    save_config(config, "agent.yaml")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from agentconfig.semantic.config_gen import AgentConfig


# ── Format detection ─────────────────────────────────────────────────────

SUPPORTED_FORMATS = {"json", "yaml", "yml", "toml"}

def _detect_format(path: str, fmt: Optional[str] = None) -> str:
    """Detect config format from file extension or explicit format string."""
    if fmt:
        fmt = fmt.lower().strip(".")
        if fmt not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format: {fmt}. Supported: {sorted(SUPPORTED_FORMATS)}")
        return fmt

    ext = Path(path).suffix.lower().strip(".")
    if ext in SUPPORTED_FORMATS:
        return ext
    raise ValueError(
        f"Cannot detect format from extension '.{ext}'. "
        f"Supported extensions: .json, .yaml, .yml, .toml. "
        f"Or pass format= explicitly."
    )


# ── Loaders ──────────────────────────────────────────────────────────────

def _load_json(path: str) -> dict:
    """Load JSON config file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_yaml(path: str) -> dict:
    """Load YAML config file."""
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "YAML support requires 'pyyaml'. Install with: pip install pyyaml"
        )
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML file must contain a mapping, got {type(data).__name__}")
    return data


def _load_toml(path: str) -> dict:
    """Load TOML config file."""
    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # Python < 3.11
        except ImportError:
            raise ImportError(
                "TOML support requires Python 3.11+ or 'tomli'. Install with: pip install tomli"
            )
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return data


_LOADERS = {
    "json": _load_json,
    "yaml": _load_yaml,
    "yml": _load_yaml,
    "toml": _load_toml,
}


# ── Savers ───────────────────────────────────────────────────────────────

def _save_json(config: AgentConfig, path: str) -> None:
    """Save config as JSON."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(config.to_json(indent=2))


def _save_yaml(config: AgentConfig, path: str) -> None:
    """Save config as YAML."""
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "YAML support requires 'pyyaml'. Install with: pip install pyyaml"
        )
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config.to_dict(), f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _save_toml(config: AgentConfig, path: str) -> None:
    """Save config as TOML."""
    try:
        import tomli_w  # Third-party TOML writer
    except ImportError:
        raise ImportError(
            "TOML write support requires 'tomli_w'. Install with: pip install tomli-w"
        )
    with open(path, "wb") as f:
        tomli_w.dump(config.to_dict(), f)


_SAVERS = {
    "json": _save_json,
    "yaml": _save_yaml,
    "yml": _save_yaml,
    "toml": _save_toml,
}


# ── Public API ───────────────────────────────────────────────────────────

def load_config(path: str, format: Optional[str] = None) -> AgentConfig:
    """
    Load an AgentConfig from a file.

    Automatically detects format from file extension (.json, .yaml, .yml, .toml).
    Can override with format= parameter.

    Args:
        path: Path to the configuration file.
        format: Optional format override ("json", "yaml", "toml").

    Returns:
        AgentConfig instance.

    Raises:
        FileNotFoundError: If the file doesn't exist.
        ValueError: If the format cannot be detected or is unsupported.
        ImportError: If required packages for the format are not installed.

    Example::

        from agentconfig.loader import load_config

        config = load_config("agent.yaml")
        print(config.name)
    """
    filepath = Path(path)
    if not filepath.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    fmt = _detect_format(path, format)
    data = _LOADERS[fmt](path)
    return AgentConfig.from_dict(data)


def save_config(config: AgentConfig, path: str, format: Optional[str] = None) -> None:
    """
    Save an AgentConfig to a file.

    Automatically detects format from file extension.
    Can override with format= parameter.

    Args:
        config: AgentConfig instance to save.
        path: Output file path.
        format: Optional format override ("json", "yaml", "toml").

    Example::

        from agentconfig.loader import save_config
        from agentconfig.semantic.config_gen import AgentConfig

        config = AgentConfig(name="My Agent")
        save_config(config, "agent.yaml")  # Save as YAML
    """
    fmt = _detect_format(path, format)
    _SAVERS[fmt](config, path)


def list_formats() -> list[str]:
    """Return list of supported config file formats."""
    return sorted(SUPPORTED_FORMATS)
