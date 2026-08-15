"""
Config Hot-Reload — zero-downtime config updates for production deployments.

Provides two mechanisms for applying config changes without a restart:

1. ``ConfigWatcher`` / ``watch_config`` — poll a config file and invoke a
   callback when its content changes.
2. ``RuntimeConfigStore`` + ``create_reload_blueprint`` — a thread-safe
   in-memory store exposed over a Flask REST API for runtime updates.

Usage (file watcher)::

    from agentconfig.hotreload import watch_config

    watcher = watch_config("agent.yaml", on_change=lambda cfg: apply(cfg))
    watcher.start()
    # ... edit agent.yaml ...
    watcher.stop()

Usage (REST API)::

    from agentconfig.hotreload import RuntimeConfigStore, create_reload_blueprint
    from flask import Flask

    store = RuntimeConfigStore()
    app = Flask(__name__)
    app.register_blueprint(create_reload_blueprint(store), url_prefix="/api")

    # PUT /api/agents/<id>/config
    # GET /api/agents/<id>/config
    # POST /api/agents/<id>/reload
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agentconfig.loader import load_config
from agentconfig.semantic.config_gen import AgentConfig
from agentconfig.versioning import ConfigVersion, ConfigVersionManager


class ConfigWatcher:
    """
    Watch a config file and invoke a callback when it changes.

    Uses mtime-based polling (thread-safe, cross-platform, no external
    dependencies such as watchdog/inotify).

    Args:
        path: Path to the config file (JSON/YAML/TOML).
        on_change: Callable invoked as ``on_change(new_config)`` on change.
        poll_interval: Seconds between polls (default 1.0).
        on_error: Optional callable invoked as ``on_error(exception)``.
    """

    def __init__(
        self,
        path: str,
        on_change: Optional[Callable[[AgentConfig], None]] = None,
        poll_interval: float = 1.0,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> None:
        self.path = Path(path)
        self.on_change = on_change
        self.poll_interval = poll_interval
        self.on_error = on_error
        self._last_mtime: Optional[float] = self._current_mtime()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _current_mtime(self) -> Optional[float]:
        try:
            return self.path.stat().st_mtime
        except OSError:
            return None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            current = self._current_mtime()
            if current is not None and current != self._last_mtime:
                self._last_mtime = current
                try:
                    config = load_config(str(self.path))
                    if self.on_change:
                        self.on_change(config)
                except Exception as e:  # noqa: BLE001
                    if self.on_error:
                        self.on_error(e)
            self._stop_event.wait(self.poll_interval)

    def start(self) -> "ConfigWatcher":
        """Start watching in a background thread (idempotent)."""
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        """Stop the background watcher thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.poll_interval + 1.0)
            self._thread = None

    def reload(self) -> Optional[AgentConfig]:
        """
        Manually reload the config file and invoke the callback if changed.

        Returns:
            The loaded AgentConfig, or None if unchanged or unreadable.
        """
        current = self._current_mtime()
        if current is not None and current != self._last_mtime:
            self._last_mtime = current
            config = load_config(str(self.path))
            if self.on_change:
                self.on_change(config)
            return config
        return None

    def __enter__(self) -> "ConfigWatcher":
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()


def watch_config(
    path: str,
    on_change: Optional[Callable[[AgentConfig], None]] = None,
    poll_interval: float = 1.0,
) -> ConfigWatcher:
    """
    Create a ConfigWatcher for a config file.

    Args:
        path: Path to the config file.
        on_change: Callable invoked with the new AgentConfig on change.
        poll_interval: Seconds between polls.

    Returns:
        A ConfigWatcher (call ``.start()`` to begin watching).
    """
    return ConfigWatcher(path, on_change=on_change, poll_interval=poll_interval)


class RuntimeConfigStore:
    """
    Thread-safe in-memory store for runtime config updates.

    Tracks the current config and full version history per agent, enabling
    runtime updates with rollback support.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._configs: Dict[str, AgentConfig] = {}
        self._histories: Dict[str, ConfigVersionManager] = {}

    def register(self, agent_id: str, config: AgentConfig) -> None:
        """Register a new agent config (initial commit)."""
        with self._lock:
            self._configs[agent_id] = config
            manager = ConfigVersionManager(name=agent_id)
            manager.commit(config, "Initial config")
            self._histories[agent_id] = manager

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        """Return the current config for an agent, or None."""
        with self._lock:
            config = self._configs.get(agent_id)
            return AgentConfig.from_dict(config.to_dict()) if config else None

    def update(self, agent_id: str, patch: Dict[str, Any], message: str = "") -> AgentConfig:
        """
        Apply a partial update to an agent's config (merged into current).

        Args:
            agent_id: The agent to update.
            patch: Dict of fields to merge into the current config.
            message: Optional commit message for the change.

        Returns:
            The updated AgentConfig.

        Raises:
            KeyError: If the agent is not registered.
        """
        with self._lock:
            if agent_id not in self._configs:
                raise KeyError(f"Unknown agent: {agent_id}")
            current = self._configs[agent_id]
            merged = current.to_dict()
            merged.update(patch)
            updated = AgentConfig.from_dict(merged)
            self._configs[agent_id] = updated
            self._histories[agent_id].commit(updated, message)
            return updated

    def history(self, agent_id: str) -> List[ConfigVersion]:
        """Return version history for an agent."""
        with self._lock:
            manager = self._histories.get(agent_id)
            return manager.history() if manager else []

    def rollback(self, agent_id: str, version_id: str) -> AgentConfig:
        """Roll back an agent's config to a previous version."""
        with self._lock:
            manager = self._histories.get(agent_id)
            if manager is None:
                raise KeyError(f"Unknown agent: {agent_id}")
            config = manager.rollback(version_id)
            self._configs[agent_id] = config
            return config

    def diff(self, agent_id: str, v1: str, v2: str) -> str:
        """Diff two versions of an agent's config."""
        with self._lock:
            manager = self._histories.get(agent_id)
            if manager is None:
                raise KeyError(f"Unknown agent: {agent_id}")
            return manager.diff(v1, v2)

    def agents(self) -> List[str]:
        """Return the list of registered agent ids."""
        with self._lock:
            return sorted(self._configs.keys())


def create_reload_blueprint(store: RuntimeConfigStore, url_prefix: str = "/api"):
    """
    Create a Flask blueprint exposing a runtime config reload REST API.

    Endpoints:
        - ``PUT    {prefix}/agents/<id>/config`` — partial config update.
        - ``GET    {prefix}/agents/<id>/config`` — fetch current config.
        - ``GET    {prefix}/agents/<id>/history`` — list version history.
        - ``POST   {prefix}/agents/<id>/rollback`` — roll back to a version.
        - ``GET    {prefix}/agents`` — list registered agents.

    Args:
        store: A RuntimeConfigStore instance.
        url_prefix: URL prefix for the blueprint (default ``/api``).

    Returns:
        A Flask Blueprint.

    Raises:
        ImportError: If Flask is not installed.
    """
    try:
        from flask import Blueprint, jsonify, request
    except ImportError:
        raise ImportError(
            "REST API support requires 'flask'. Install with: pip install flask"
        )

    bp = Blueprint("agentconfig_reload", __name__, url_prefix=url_prefix)

    @bp.route("/agents", methods=["GET"])
    def list_agents():
        return jsonify({"agents": store.agents()})

    @bp.route("/agents/<agent_id>/config", methods=["PUT"])
    def update_config(agent_id: str):
        patch = request.get_json(silent=True) or {}
        if not isinstance(patch, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400
        try:
            updated = store.update(agent_id, patch, message=request.args.get("message", ""))
        except KeyError as e:
            return jsonify({"error": str(e)}), 404
        return jsonify(updated.to_dict())

    @bp.route("/agents/<agent_id>/config", methods=["GET"])
    def get_config(agent_id: str):
        config = store.get(agent_id)
        if config is None:
            return jsonify({"error": f"Unknown agent: {agent_id}"}), 404
        return jsonify(config.to_dict())

    @bp.route("/agents/<agent_id>/history", methods=["GET"])
    def get_history(agent_id: str):
        try:
            history = store.history(agent_id)
        except KeyError as e:
            return jsonify({"error": str(e)}), 404
        return jsonify({"history": [v.to_dict() for v in history]})

    @bp.route("/agents/<agent_id>/rollback", methods=["POST"])
    def rollback_config(agent_id: str):
        body = request.get_json(silent=True) or {}
        version_id = body.get("version")
        if not version_id:
            return jsonify({"error": "Request body must include 'version'"}), 400
        try:
            config = store.rollback(agent_id, version_id)
        except KeyError as e:
            return jsonify({"error": str(e)}), 404
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify(config.to_dict())

    return bp
