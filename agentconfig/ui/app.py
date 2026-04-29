"""
AgentConfig Web UI — Flask application.

Provides:
  GET  /                     → Dashboard (monitoring view)
  GET  /configure            → Agent configuration wizard
  POST /api/parse-intent     → Parse business description → intent JSON
  POST /api/generate-config  → Generate full AgentConfig
  GET  /api/configs          → List all saved configs
  GET  /api/configs/<id>     → Get a specific config
  POST /api/configs          → Save a config
  DELETE /api/configs/<id>   → Delete a config
  POST /api/chat             → Chat with a configured agent (demo)
  GET  /api/stats            → Monitor stats
  GET  /api/runs             → Recent run records
  POST /api/runs/clear       → Clear run history
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Dict

from flask import Flask, request, jsonify, send_from_directory

from agentconfig.semantic.intent import IntentParser, AgentIntent
from agentconfig.semantic.constraint import Constraint, ConstraintEngine
from agentconfig.semantic.config_gen import ConfigGenerator, AgentConfig, ModelConfig
from agentconfig.runtime.executor import AgentExecutor
from agentconfig.runtime.monitor import AgentMonitor

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

_HERE     = Path(__file__).parent
_STATIC   = _HERE / "static"
_DATA_DIR = Path(os.environ.get("AGENTCONFIG_DATA", ".agentconfig_data"))
_DATA_DIR.mkdir(exist_ok=True)
(_DATA_DIR / "configs").mkdir(exist_ok=True)

app      = Flask(__name__, static_folder=str(_STATIC), static_url_path="/static")
_parser  = IntentParser()
_gen     = ConfigGenerator()
_monitor = AgentMonitor()
_executor = AgentExecutor()          # Uses mock LLM by default
_sessions: Dict[str, str] = {}       # session_id → config_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config_path(config_id: str) -> Path:
    return _DATA_DIR / "configs" / f"{config_id}.json"


def _load_all_configs() -> list:
    configs = []
    for p in (_DATA_DIR / "configs").glob("*.json"):
        try:
            cfg = AgentConfig.load(str(p))
            configs.append({
                "config_id":   cfg.config_id,
                "name":        cfg.name,
                "version":     cfg.version,
                "description": cfg.description,
                "created_at":  cfg.created_at,
                "domain":      cfg.intent.domain.value if cfg.intent else "general",
            })
        except Exception:
            pass
    configs.sort(key=lambda c: c["created_at"], reverse=True)
    return configs


def _seed_demo_data():
    """Create demo run records so the dashboard isn't empty on first launch."""
    from agentconfig.runtime.executor import RunRecord, RunStatus, Turn
    from datetime import datetime, timedelta, timezone
    import random

    statuses = [RunStatus.COMPLETED, RunStatus.COMPLETED, RunStatus.COMPLETED,
                RunStatus.ESCALATED, RunStatus.ERROR]
    agents   = ["Customer Support Bot", "Sales Assistant", "HR Helper"]

    base = datetime.now(timezone.utc)
    for i in range(30):
        r = RunRecord(
            config_id=f"demo-{i % 3}",
            agent_name=agents[i % len(agents)],
            status=random.choice(statuses),
        )
        r.started_at = (base - timedelta(minutes=i * 3)).isoformat()
        r.ended_at   = (base - timedelta(minutes=i * 3 - 1)).isoformat()
        r.total_latency_ms = random.uniform(300, 2500)

        # Add some turns
        for j in range(random.randint(1, 5)):
            r.turns.append(Turn(role="user",      content=f"User message {j}"))
            r.turns.append(Turn(role="assistant", content=f"Agent response {j}",
                                latency_ms=random.uniform(200, 800)))

        # Occasionally add violations
        if random.random() < 0.2:
            r.turns[-1].constraint_violations = [{
                "id": "auto-forbidden-topic-0",
                "type": "forbidden_topic",
                "message": "Forbidden topic detected",
                "action": "warn",
            }]
        _monitor.record(r)


_seed_demo_data()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(str(_STATIC), "index.html")


@app.route("/configure")
def configure():
    return send_from_directory(str(_STATIC), "configure.html")


@app.route("/configs")
def configs_page():
    return send_from_directory(str(_STATIC), "configs.html")


@app.route("/chat")
def chat_page():
    return send_from_directory(str(_STATIC), "chat.html")


# ---------------------------------------------------------------------------
# API — Intent parsing
# ---------------------------------------------------------------------------

@app.route("/api/parse-intent", methods=["POST"])
def api_parse_intent():
    data        = request.get_json(force=True)
    description = data.get("description", "").strip()
    name        = data.get("name", "My Agent").strip()

    if not description:
        return jsonify({"error": "description is required"}), 400

    try:
        intent = _parser.parse(description=description, name=name)
        return jsonify({"intent": intent.to_dict(), "system_prompt": intent.to_system_prompt()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# API — Config CRUD
# ---------------------------------------------------------------------------

@app.route("/api/generate-config", methods=["POST"])
def api_generate_config():
    data = request.get_json(force=True)

    # Rebuild intent from dict or from raw description
    if data.get("intent"):
        intent = AgentIntent.from_dict(data["intent"])
    elif data.get("description"):
        intent = _parser.parse(data["description"], name=data.get("name", "My Agent"))
    else:
        return jsonify({"error": "intent or description is required"}), 400

    model_data = data.get("model", {})
    model = ModelConfig(
        provider   = model_data.get("provider", "openai"),
        model      = model_data.get("model", "gpt-4o-mini"),
        temperature= float(model_data.get("temperature", 0.7)),
        max_tokens = int(model_data.get("max_tokens", 1024)),
    )

    # Extra constraints from UI
    extra = []
    for c in data.get("extra_constraints", []):
        try:
            extra.append(Constraint.from_dict(c))
        except Exception:
            pass

    config = _gen.generate(intent=intent, model=model, extra_constraints=extra)
    return jsonify({"config": config.to_dict()})


@app.route("/api/configs", methods=["GET"])
def api_list_configs():
    return jsonify({"configs": _load_all_configs()})


@app.route("/api/configs", methods=["POST"])
def api_save_config():
    data = request.get_json(force=True)
    cfg_dict = data.get("config")
    if not cfg_dict:
        return jsonify({"error": "config is required"}), 400

    try:
        cfg = AgentConfig.from_dict(cfg_dict)
        cfg.save(str(_config_path(cfg.config_id)))
        return jsonify({"config_id": cfg.config_id, "message": "Saved successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/configs/<config_id>", methods=["GET"])
def api_get_config(config_id: str):
    p = _config_path(config_id)
    if not p.exists():
        return jsonify({"error": "Config not found"}), 404
    cfg = AgentConfig.load(str(p))
    return jsonify({"config": cfg.to_dict()})


@app.route("/api/configs/<config_id>", methods=["DELETE"])
def api_delete_config(config_id: str):
    p = _config_path(config_id)
    if p.exists():
        p.unlink()
        return jsonify({"message": "Deleted."})
    return jsonify({"error": "Config not found"}), 404


# ---------------------------------------------------------------------------
# API — Chat (demo)
# ---------------------------------------------------------------------------

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data       = request.get_json(force=True)
    config_id  = data.get("config_id")
    user_input = data.get("message", "").strip()
    session_id = data.get("session_id") or str(uuid.uuid4())[:8]

    if not user_input:
        return jsonify({"error": "message is required"}), 400

    # Load config
    if config_id:
        p = _config_path(config_id)
        if not p.exists():
            return jsonify({"error": "Config not found"}), 404
        config = AgentConfig.load(str(p))
    else:
        # Use a minimal default config for demo
        config = AgentConfig(name="Demo Agent", system_prompt="You are a helpful assistant.")

    response, record = _executor.chat(config, user_input, session_id=session_id)
    _monitor.record(record)

    return jsonify({
        "response":   response,
        "session_id": session_id,
        "run_id":     record.run_id,
        "status":     record.status.value,
        "violations": [
            v for turn in record.turns
            for v in turn.constraint_violations
        ],
    })


# ---------------------------------------------------------------------------
# API — Monitoring
# ---------------------------------------------------------------------------

@app.route("/api/stats", methods=["GET"])
def api_stats():
    agent_name = request.args.get("agent")
    return jsonify(_monitor.stats(agent_name=agent_name))


@app.route("/api/runs", methods=["GET"])
def api_runs():
    n          = int(request.args.get("n", 50))
    agent_name = request.args.get("agent")
    return jsonify({"runs": _monitor.recent(n=n, agent_name=agent_name)})


@app.route("/api/runs/clear", methods=["POST"])
def api_clear_runs():
    _monitor.clear()
    _seed_demo_data()
    return jsonify({"message": "Run history cleared and demo data reloaded."})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(host: str = "127.0.0.1", port: int = 7860, debug: bool = False):
    print(f"\nAgentConfig UI running at http://{host}:{port}")
    print("  Dashboard:  http://{}:{}/".format(host, port))
    print("  Configure:  http://{}:{}/configure".format(host, port))
    print("  My Configs: http://{}:{}/configs".format(host, port))
    print("  Chat:       http://{}:{}/chat".format(host, port))
    print("\nPress Ctrl+C to stop.\n")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run(debug=True)
