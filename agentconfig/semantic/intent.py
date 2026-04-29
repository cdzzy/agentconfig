"""
Intent Parser — Converts business language descriptions into structured AgentIntent.

Business users describe what they want in plain language:
  "This agent helps our customer service team reply to complaints.
   It should always be polite, never mention pricing, and escalate
   when the customer is angry."

IntentParser extracts:
- purpose: what the agent does
- audience: who uses / is served by the agent
- tone: communication style
- domain: business domain (customer_service, sales, hr, etc.)
- actions_allowed: explicit allowances
- actions_forbidden: explicit prohibitions
- escalation_triggers: conditions to hand off to a human
- goals: measurable objectives
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class AgentTone(str, Enum):
    PROFESSIONAL = "professional"
    FRIENDLY     = "friendly"
    FORMAL       = "formal"
    CASUAL       = "casual"
    EMPATHETIC   = "empathetic"
    CONCISE      = "concise"


class AgentDomain(str, Enum):
    CUSTOMER_SERVICE = "customer_service"
    SALES            = "sales"
    HR               = "hr"
    FINANCE          = "finance"
    IT_SUPPORT       = "it_support"
    LEGAL            = "legal"
    MARKETING        = "marketing"
    GENERAL          = "general"


@dataclass
class AgentIntent:
    """Structured representation of what a business user wants from an agent."""

    # Core identity
    name: str = "My Agent"
    purpose: str = ""
    audience: str = ""
    domain: AgentDomain = AgentDomain.GENERAL

    # Behavioral style
    tone: List[AgentTone] = field(default_factory=lambda: [AgentTone.PROFESSIONAL])
    language: str = "auto"          # auto-detect, or ISO code like "en", "zh"

    # What it can/cannot do
    actions_allowed: List[str]   = field(default_factory=list)
    actions_forbidden: List[str] = field(default_factory=list)
    topics_forbidden: List[str]  = field(default_factory=list)

    # Escalation & safety
    escalation_triggers: List[str] = field(default_factory=list)
    max_turns: int = 20
    require_confirmation: List[str] = field(default_factory=list)

    # Goals
    goals: List[str] = field(default_factory=list)

    # Raw source
    raw_description: str = ""

    def to_system_prompt(self) -> str:
        """Generate a system prompt from this intent."""
        lines = []

        if self.purpose:
            lines.append(f"You are {self.name}. {self.purpose}")
        if self.audience:
            lines.append(f"You serve: {self.audience}")

        if self.tone:
            tone_desc = ", ".join(t.value for t in self.tone)
            lines.append(f"Your communication style should be: {tone_desc}.")

        if self.actions_allowed:
            lines.append("You are allowed to: " + "; ".join(self.actions_allowed) + ".")

        if self.actions_forbidden:
            lines.append("You must NEVER: " + "; ".join(self.actions_forbidden) + ".")

        if self.topics_forbidden:
            lines.append("Never discuss or mention: " + ", ".join(self.topics_forbidden) + ".")

        if self.escalation_triggers:
            conds = "; ".join(self.escalation_triggers)
            lines.append(
                f"If any of these conditions arise, immediately tell the user a human specialist "
                f"will take over: {conds}."
            )

        if self.require_confirmation:
            actions = ", ".join(self.require_confirmation)
            lines.append(f"Always ask for explicit confirmation before: {actions}.")

        if self.goals:
            lines.append("Your success goals: " + "; ".join(self.goals) + ".")

        return "\n\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "name":                 self.name,
            "purpose":              self.purpose,
            "audience":             self.audience,
            "domain":               self.domain.value,
            "tone":                 [t.value for t in self.tone],
            "language":             self.language,
            "actions_allowed":      self.actions_allowed,
            "actions_forbidden":    self.actions_forbidden,
            "topics_forbidden":     self.topics_forbidden,
            "escalation_triggers":  self.escalation_triggers,
            "max_turns":            self.max_turns,
            "require_confirmation": self.require_confirmation,
            "goals":                self.goals,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AgentIntent":
        obj = cls()
        obj.name                 = d.get("name", "My Agent")
        obj.purpose              = d.get("purpose", "")
        obj.audience             = d.get("audience", "")
        obj.domain               = AgentDomain(d.get("domain", "general"))
        obj.tone                 = [AgentTone(t) for t in d.get("tone", ["professional"])]
        obj.language             = d.get("language", "auto")
        obj.actions_allowed      = d.get("actions_allowed", [])
        obj.actions_forbidden    = d.get("actions_forbidden", [])
        obj.topics_forbidden     = d.get("topics_forbidden", [])
        obj.escalation_triggers  = d.get("escalation_triggers", [])
        obj.max_turns            = d.get("max_turns", 20)
        obj.require_confirmation = d.get("require_confirmation", [])
        obj.goals                = d.get("goals", [])
        return obj


# ---------------------------------------------------------------------------
# Keyword mappings for rule-based parsing (no LLM required)
# ---------------------------------------------------------------------------

_DOMAIN_KEYWORDS: dict[AgentDomain, List[str]] = {
    AgentDomain.CUSTOMER_SERVICE: ["customer", "complaint", "support", "service", "refund", "ticket", "客服", "投诉"],
    AgentDomain.SALES:            ["sales", "lead", "deal", "revenue", "quote", "pricing", "销售", "报价"],
    AgentDomain.HR:               ["hr", "human resource", "employee", "onboard", "leave", "payroll", "人事", "员工"],
    AgentDomain.FINANCE:          ["finance", "invoice", "budget", "expense", "accounting", "财务", "报销"],
    AgentDomain.IT_SUPPORT:       ["it", "technical", "system", "access", "password", "ticket", "运维", "技术支持"],
    AgentDomain.LEGAL:            ["legal", "contract", "compliance", "regulation", "clause", "法务", "合规"],
    AgentDomain.MARKETING:        ["marketing", "campaign", "brand", "content", "social media", "营销", "品牌"],
}

_TONE_KEYWORDS: dict[AgentTone, List[str]] = {
    AgentTone.FRIENDLY:      ["friendly", "warm", "welcoming", "polite", "礼貌", "友好", "亲切"],
    AgentTone.FORMAL:        ["formal", "official", "正式", "官方"],
    AgentTone.PROFESSIONAL:  ["professional", "expert", "专业", "专家"],
    AgentTone.EMPATHETIC:    ["empathetic", "compassionate", "understanding", "caring", "同理", "理解", "关怀"],
    AgentTone.CONCISE:       ["concise", "brief", "short", "succinct", "简洁", "简短", "精简"],
    AgentTone.CASUAL:        ["casual", "informal", "relaxed", "conversational", "随意", "轻松", "口语"],
}

_FORBIDDEN_PATTERNS = [
    r"never\s+(?:mention|discuss|talk about|reveal)\s+([^.,;]+)",
    r"do not\s+(?:mention|discuss|share|disclose)\s+([^.,;]+)",
    r"must not\s+(?:mention|discuss|share)\s+([^.,;]+)",
    r"不(?:得|能|要)\s*(?:提及|讨论|透露)\s*([^，。；]+)",
]

_ESCALATION_PATTERNS = [
    r"escalate\s+(?:when|if)\s+([^.,;]+)",
    r"hand(?:\s+off|\s*over)\s+(?:when|if)\s+([^.,;]+)",
    r"transfer\s+(?:when|if|to human when)\s+([^.,;]+)",
    r"当([^，。；]+)时.*?转.*?人工",
    r"如果([^，。；]+).*?升级",
]

_CONFIRMATION_PATTERNS = [
    r"(?:always\s+)?(?:ask|confirm|get approval)\s+(?:before|prior to)\s+([^.,;]+)",
    r"require\s+confirmation\s+(?:for|before|when)\s+([^.,;]+)",
    r"在([^，。；]+)前.*?确认",
]


class IntentParser:
    """
    Parse a plain-language business description into a structured AgentIntent.

    Two modes:
      1. Rule-based (default) — fast, no external dependencies, works offline.
      2. LLM-assisted — pass an llm_fn callable to use an LLM for richer extraction.

    Example (rule-based)::

        parser = IntentParser()
        intent = parser.parse(
            description="This agent handles customer complaints. It must be polite "
                        "and empathetic, never mention competitor products, and "
                        "escalate when the customer asks for a refund over $500.",
            name="Complaint Handler"
        )
        print(intent.to_system_prompt())

    Example (LLM-assisted)::

        import openai
        def my_llm(prompt: str) -> str:
            resp = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}]
            )
            return resp.choices[0].message.content

        parser = IntentParser(llm_fn=my_llm)
        intent = parser.parse(description="...", name="Sales Bot")
    """

    def __init__(self, llm_fn=None):
        """
        Args:
            llm_fn: Optional callable (str) -> str for LLM-assisted parsing.
        """
        self._llm_fn = llm_fn

    # ------------------------------------------------------------------
    def parse(self, description: str, name: str = "My Agent") -> AgentIntent:
        """Parse description into AgentIntent."""
        if self._llm_fn:
            return self._parse_with_llm(description, name)
        return self._parse_rule_based(description, name)

    # ------------------------------------------------------------------
    def _parse_rule_based(self, description: str, name: str) -> AgentIntent:
        intent = AgentIntent(name=name, raw_description=description)
        text_lower = description.lower()

        # Domain detection
        best_domain = AgentDomain.GENERAL
        best_score  = 0
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > best_score:
                best_score = score
                best_domain = domain
        intent.domain = best_domain

        # Tone detection
        tones: List[AgentTone] = []
        for tone, keywords in _TONE_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                tones.append(tone)
        if not tones:
            tones = [AgentTone.PROFESSIONAL]
        intent.tone = tones

        # Purpose — first sentence heuristic
        sentences = re.split(r'[.!?\n]', description)
        if sentences:
            intent.purpose = sentences[0].strip()

        # Forbidden topics
        forbidden: List[str] = []
        for pat in _FORBIDDEN_PATTERNS:
            for m in re.finditer(pat, description, re.IGNORECASE):
                item = m.group(1).strip().rstrip(".,;")
                if item:
                    forbidden.append(item)
        intent.topics_forbidden = forbidden

        # Escalation triggers
        escalations: List[str] = []
        for pat in _ESCALATION_PATTERNS:
            for m in re.finditer(pat, description, re.IGNORECASE):
                item = m.group(1).strip().rstrip(".,;")
                if item:
                    escalations.append(item)
        intent.escalation_triggers = escalations

        # Confirmation requirements
        confirmations: List[str] = []
        for pat in _CONFIRMATION_PATTERNS:
            for m in re.finditer(pat, description, re.IGNORECASE):
                item = m.group(1).strip().rstrip(".,;")
                if item:
                    confirmations.append(item)
        intent.require_confirmation = confirmations

        return intent

    # ------------------------------------------------------------------
    def _parse_with_llm(self, description: str, name: str) -> AgentIntent:
        """Use LLM to extract structured intent from description."""
        prompt = f"""You are an AI configuration specialist. Extract structured information from the following business description of an AI agent.

Business description:
\"\"\"{description}\"\"\"

Return a JSON object with these fields:
- purpose (string): what the agent does, 1-2 sentences
- audience (string): who the agent serves
- domain (string): one of: customer_service, sales, hr, finance, it_support, legal, marketing, general
- tone (array of strings): from: professional, friendly, formal, casual, empathetic, concise
- language (string): "auto" or ISO code
- actions_allowed (array of strings): things the agent is explicitly allowed to do
- actions_forbidden (array of strings): things the agent must never do
- topics_forbidden (array of strings): topics the agent must never discuss
- escalation_triggers (array of strings): conditions that require human handoff
- require_confirmation (array of strings): actions that need user confirmation before proceeding
- goals (array of strings): success criteria

Return ONLY valid JSON, no markdown, no explanation."""

        raw = self._llm_fn(prompt)

        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw.strip(), flags=re.MULTILINE)

        import json
        data = json.loads(raw)
        intent = AgentIntent.from_dict(data)
        intent.name = name
        intent.raw_description = description
        return intent
