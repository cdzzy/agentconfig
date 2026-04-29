"""
AgentConfig Examples — Launch the Web UI
=========================================

Run this file to start the AgentConfig web interface:
  http://localhost:7860
"""

from agentconfig.ui.app import run

if __name__ == "__main__":
    run(host="127.0.0.1", port=7860, debug=False)
