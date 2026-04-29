"""
AgentConfig Examples - Healthcare Assistant Agent
==================================================

Shows how to configure a healthcare AI assistant that follows
medical compliance rules and provides safe, accurate information.

Healthcare agents require extra care around:
- Patient privacy (HIPAA/GDPR compliance)
- Medical disclaimers
- Scope of practice limitations
- Drug interaction warnings
"""

from agentconfig.semantic.intent import IntentParser
from agentconfig.semantic.constraint import Constraint, ConstraintType, ConstraintAction
from agentconfig.semantic.config_gen import ConfigGenerator, ModelConfig
from agentconfig.runtime.executor import AgentExecutor

# ── 1. Define the agent's role and boundaries ─────────────────────────────────
parser = IntentParser()
intent = parser.parse(
    description="""
    This agent serves as a health information assistant for patients.
    It provides general health information and wellness guidance.
    Always include appropriate medical disclaimers.
    Never diagnose conditions or prescribe treatments.
    Never request or store personal health information (PHI).
    Decline to answer questions about specific medical treatments
    without proper medical supervision.
    Escalate immediately if user mentions suicidal ideation or self-harm.
    """,
    name="Health Info Bot",
)

print("=== Parsed Intent ===")
print(f"  Name:        {intent.name}")
print(f"  Domain:      {intent.domain.value}")
print(f"  Tone:        {[t.value for t in intent.tone]}")
print(f"  Forbidden:   {intent.topics_forbidden}")
print(f"  Escalate:    {intent.escalation_triggers}")
print()

# ── 2. Generate config with medical-specific constraints ─────────────────────
gen = ConfigGenerator()
config = gen.generate(
    intent=intent,
    model=ModelConfig(
        provider="openai",
        model="gpt-4o-mini",
        temperature=0.3,  # Lower temp for more consistent responses
    ),
    extra_constraints=[
        # Medical disclaimer requirement
        Constraint(
            id="medical-disclaimer",
            type=ConstraintType.FORBIDDEN_KEYWORD,
            description="Must always include disclaimer when providing health info",
            keywords=["#NOMEDINFO#"],  # Marker to detect missing disclaimer
            action=ConstraintAction.WARN,
        ),
        # No diagnosis
        Constraint(
            id="no-diagnosis",
            type=ConstraintType.FORBIDDEN_KEYWORD,
            description="Cannot provide diagnosis",
            keywords=["diagnosis", "diagnosed as", "you have"],
            action=ConstraintAction.BLOCK,
        ),
        # No prescription
        Constraint(
            id="no-prescription",
            type=ConstraintType.FORBIDDEN_KEYWORD,
            description="Cannot prescribe medications",
            keywords=["prescribe", "take this medication", "your prescription"],
            action=ConstraintAction.BLOCK,
        ),
        # Privacy protection
        Constraint(
            id="no-phi",
            type=ConstraintType.FORBIDDEN_KEYWORD,
            description="Cannot request sensitive health data",
            keywords=["social security", "insurance id", "patient id"],
            action=ConstraintAction.BLOCK,
        ),
    ],
)

print("=== Generated Config ===")
print(f"  Config ID:   {config.config_id}")
print(f"  Constraints: {len(config.constraints)}")
print()

# ── 3. Test the agent ──────────────────────────────────────────────────────────
executor = AgentExecutor()

test_messages = [
    "What are the symptoms of diabetes?",
    "I think I have COVID, should I take antibiotics?",
    "Can you tell me my diagnosis based on my symptoms?",
    "Give me a prescription for ibuprofen",
]

session = "healthcare-demo-001"
print("=== Conversation Test ===")
for msg in test_messages:
    response, record = executor.chat(config, msg, session_id=session)
    print(f"\nUser:  {msg}")
    print(f"Agent: {response[:300]}..." if len(response) > 300 else f"\nAgent: {response}")
    if record.turns and record.turns[-1].constraint_violations:
        violations = record.turns[-1].constraint_violations
        print(f"  [VIOLATIONS: {len(violations)} - {[v.constraint_id for v in violations]}]")

# ── 4. Save config for production use ────────────────────────────────────────
config.save("healthcare_bot_config.json")
print("\n\nConfig saved to: healthcare_bot_config.json")
