"""
AgentConfig Examples — Customer Support Agent
=============================================

Shows how to configure and run a customer service agent
without writing any complex code.
"""

from agentconfig.semantic.intent import IntentParser
from agentconfig.semantic.constraint import Constraint, ConstraintType, ConstraintAction
from agentconfig.semantic.config_gen import ConfigGenerator, ModelConfig
from agentconfig.runtime.executor import AgentExecutor
from agentconfig.runtime.monitor import AgentMonitor

# ── 1. Describe your agent in plain language ──────────────────────────────
parser = IntentParser()
intent = parser.parse(
    description="""
    This agent handles customer service inquiries for our e-commerce platform.
    It should always be polite, empathetic, and patient.
    It must never mention competitor products or reveal internal pricing margins.
    Always confirm before processing any refund over $200.
    Escalate when the customer uses abusive language or explicitly asks for a manager.
    """,
    name="Support Bot",
)

print("=== Parsed Intent ===")
print(f"  Name:      {intent.name}")
print(f"  Domain:    {intent.domain.value}")
print(f"  Tone:      {[t.value for t in intent.tone]}")
print(f"  Forbidden: {intent.topics_forbidden}")
print(f"  Escalate:  {intent.escalation_triggers}")
print()

# ── 2. Generate a full AgentConfig ────────────────────────────────────────
gen = ConfigGenerator()
config = gen.generate(
    intent=intent,
    model=ModelConfig(
        provider="openai",
        model="gpt-4o-mini",
        temperature=0.4,
    ),
    extra_constraints=[
        Constraint(
            id="no-pricing",
            type=ConstraintType.FORBIDDEN_KEYWORD,
            description="Never reveal pricing margins or internal costs",
            keywords=["margin", "markup", "cost price", "wholesale"],
            action=ConstraintAction.BLOCK,
        ),
    ],
)

print("=== Generated Config ===")
print(f"  Config ID:   {config.config_id}")
print(f"  Constraints: {len(config.constraints)}")
print()
print("=== System Prompt Preview ===")
print(config.system_prompt[:400])
print()

# ── 3. Run the agent with constraint checking ─────────────────────────────
monitor  = AgentMonitor()
executor = AgentExecutor()   # Uses mock LLM — replace with real LLM for production

print("=== Conversation Test ===")
test_messages = [
    "Hello, I need help with my order.",
    "My package never arrived and I want a refund.",
    "What is your profit margin on this item?",   # Should be blocked
    "I want to speak to a manager right now!",     # Should escalate
]

session = "demo-session-001"
for msg in test_messages:
    response, record = executor.chat(config, msg, session_id=session)
    print(f"\nUser:  {msg}")
    print(f"Agent: {response}")
    if record.turns and record.turns[-1].constraint_violations:
        print(f"  [VIOLATIONS DETECTED: {len(record.turns[-1].constraint_violations)}]")
    if record.status.value == "escalated":
        print(f"  [ESCALATED: {record.escalation_reason}]")
    monitor.record(record)

# ── 4. Check monitoring stats ─────────────────────────────────────────────
print("\n=== Monitor Stats ===")
stats = monitor.stats()
print(f"  Total runs:       {stats['total_runs']}")
print(f"  Total violations: {stats['total_violations']}")
print(f"  Violation types:  {stats['violation_by_type']}")

# ── 5. Save config to file ────────────────────────────────────────────────
config.save("support_bot_config.json")
print("\nConfig saved to: support_bot_config.json")

# ── 6. Load config back ───────────────────────────────────────────────────
from agentconfig.semantic.config_gen import AgentConfig
loaded = AgentConfig.load("support_bot_config.json")
print(f"Loaded config: {loaded.name} (ID: {loaded.config_id})")

import os
os.remove("support_bot_config.json")
