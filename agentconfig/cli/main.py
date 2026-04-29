"""
AgentConfig CLI - Command line interface.

Usage:
    agentconfig serve [--config FILE] [--port PORT]
    agentconfig create [--template TEMPLATE] [--output FILE]
    agentconfig validate [--config FILE]
    agentconfig list-templates
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from ..semantic.intent import IntentParser
from ..semantic.config_gen import ConfigGenerator
from ..semantic.constraint import ConstraintEngine


def get_templates() -> dict:
    """Get available agent templates."""
    return {
        "customer-service": {
            "description": "Handles customer inquiries and complaints",
            "intent": """This agent handles customer complaints.
It should be polite and empathetic.
Never mention competitor products or internal pricing.
Escalate when the customer asks for a manager.""",
        },
        "sales": {
            "description": "Assists with product recommendations and sales",
            "intent": """This agent helps customers find the right products.
Be enthusiastic but not pushy.
Always mention current promotions.
Never make promises about delivery dates.""",
        },
        "technical-support": {
            "description": "Provides technical troubleshooting assistance",
            "intent": """This agent helps users solve technical problems.
Be patient and explain step by step.
Never ask for passwords or sensitive credentials.
Escalate to human support for complex issues.""",
        },
        "content-moderator": {
            "description": "Reviews and moderates user-generated content",
            "intent": """This agent reviews content for policy violations.
Be fair and consistent in decisions.
Flag hate speech, spam, and inappropriate content.
Preserve context when escalating edge cases.""",
        },
        "research-agent": {
            "description": "Deep research agent for AI-powered investigation (inspired by AI-Scientist patterns)",
            "intent": """This agent conducts thorough research on user queries.
It should be factual, cite sources, and verify claims.
Never fabricate citations or present speculation as fact.
Break complex topics into sub-questions.
Synthesize findings into clear, structured reports.
Present uncertainty and confidence levels.
Always explore multiple perspectives before concluding.""",
        },
    }


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the web UI server."""
    from ..ui.app import app
    
    port = args.port or 7860
    config_file = args.config
    
    if config_file:
        print(f"Loading configuration from: {config_file}")
    
    print(f"Starting AgentConfig server on http://localhost:{port}")
    print(f"Dashboard: http://localhost:{port}/")
    print(f"Configure: http://localhost:{port}/configure")
    print("Press Ctrl+C to stop")
    
    try:
        app.run(host="0.0.0.0", port=port, debug=False)
    except KeyboardInterrupt:
        print("\nShutting down...")
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    """Create a new agent configuration from template or description."""
    templates = get_templates()
    
    if args.template:
        if args.template not in templates:
            print(f"Error: Unknown template '{args.template}'", file=sys.stderr)
            print(f"Available templates: {', '.join(templates.keys())}", file=sys.stderr)
            return 1
        
        description = templates[args.template]["intent"]
        print(f"Using template: {args.template}")
        print(f"Description: {templates[args.template]['description']}")
    else:
        print("Enter a description of your agent (press Ctrl+D or Ctrl+Z when done):")
        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass
        description = "\n".join(lines)
    
    if not description.strip():
        print("Error: No description provided", file=sys.stderr)
        return 1
    
    # Parse intent and generate config
    print("\nParsing intent...")
    parser = IntentParser()
    intent = parser.parse(description, name=args.template or "Custom Agent")
    
    print(f"Detected domain: {intent.domain.value}")
    print(f"Detected tone: {[t.value for t in intent.tone]}")
    
    print("\nGenerating configuration...")
    generator = ConfigGenerator()
    config = generator.generate(intent)
    
    # Output
    output_data = {
        "name": config.name,
        "system_prompt": config.system_prompt,
        "constraints": [
            {
                "type": c.type.value,
                "action": c.action.value,
                "params": c.params,
            }
            for c in config.constraints
        ],
        "max_turns": config.max_turns,
        "metadata": config.metadata,
    }
    
    output_json = json.dumps(output_data, indent=2, ensure_ascii=False)
    
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output_json, encoding="utf-8")
        print(f"\nConfiguration saved to: {output_path.absolute()}")
    else:
        print("\n--- Generated Configuration ---")
        print(output_json)
    
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate an existing configuration file."""
    config_file = args.config
    
    if not config_file:
        print("Error: --config is required for validation", file=sys.stderr)
        return 1
    
    config_path = Path(config_file)
    if not config_path.exists():
        print(f"Error: Configuration file not found: {config_file}", file=sys.stderr)
        return 1
    
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in configuration file: {e}", file=sys.stderr)
        return 1
    
    # Validate required fields
    required_fields = ["name", "system_prompt"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        print(f"Error: Missing required fields: {', '.join(missing)}", file=sys.stderr)
        return 1
    
    # Validate constraints
    if "constraints" in data:
        engine = ConstraintEngine()
        for i, c in enumerate(data["constraints"]):
            if "type" not in c:
                print(f"Error: Constraint {i} missing 'type' field", file=sys.stderr)
                return 1
            if "action" not in c:
                print(f"Error: Constraint {i} missing 'action' field", file=sys.stderr)
                return 1
    
    print(f"✅ Configuration is valid: {config_path.absolute()}")
    print(f"   Name: {data['name']}")
    print(f"   Constraints: {len(data.get('constraints', []))}")
    
    return 0


def cmd_list_templates(args: argparse.Namespace) -> int:
    """List available agent templates."""
    templates = get_templates()
    
    print("Available Agent Templates:")
    print("-" * 50)
    
    for name, info in templates.items():
        print(f"\n{name}")
        print(f"  {info['description']}")
    
    print(f"\n\nUse 'agentconfig create --template <name>' to create from a template")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Export a configuration to a specific format."""
    config_file = args.config
    
    if not config_file:
        print("Error: --config is required for export", file=sys.stderr)
        return 1
    
    config_path = Path(config_file)
    if not config_path.exists():
        print(f"Error: Configuration file not found: {config_file}", file=sys.stderr)
        return 1
    
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in configuration file: {e}", file=sys.stderr)
        return 1
    
    if args.format == "langchain":
        output = _export_langchain(data)
    elif args.format == "langgraph":
        output = _export_langgraph(data)
    elif args.format == "openai":
        output = _export_openai(data)
    elif args.format == "a2a":
        output = _export_a2a(data)
    else:
        print(f"Error: Unknown format '{args.format}'", file=sys.stderr)
        print(f"Supported formats: langchain, langgraph, openai, a2a", file=sys.stderr)
        return 1
    
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output, encoding="utf-8")
        print(f"Exported to: {output_path.absolute()}")
    else:
        print(output)
    
    return 0


def _export_langchain(config: dict) -> str:
    """Export to LangChain prompt template format."""
    system_prompt = config.get("system_prompt", "")
    constraints = config.get("constraints", [])
    
    # Build constraint instructions
    constraint_texts = []
    for c in constraints:
        ctype = c.get("type", "")
        action = c.get("action", "")
        params = c.get("params", {})
        
        if ctype == "forbidden_keyword":
            keywords = params.get("keywords", [])
            constraint_texts.append(f"- NEVER mention or discuss: {', '.join(keywords)}")
        elif ctype == "max_length":
            max_len = params.get("max_length", "")
            constraint_texts.append(f"- Keep responses under {max_len} characters")
        elif ctype == "forbidden_topic":
            topics = params.get("topics", [])
            constraint_texts.append(f"- Do not discuss these topics: {', '.join(topics)}")
    
    constraints_section = "\n".join(constraint_texts) if constraint_texts else ""
    
    output = f'''"""
LangChain Prompt Template for {config.get("name", "Agent")}

Generated by AgentConfig.
To use:
    from langchain_core.prompts import ChatPromptTemplate
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{{human_input}}"),
    ])
"""

SYSTEM_PROMPT = """
{system_prompt}
{constraints_section}
""".strip()

# Example usage with LangChain:
# from langchain_openai import ChatOpenAI
# from langchain_core.output_parsers import StrOutputParser
# 
# chain = prompt | ChatOpenAI(model="gpt-4o") | StrOutputParser()
# result = chain.invoke({{"human_input": "Hello!"}})
'''
    return output


def _export_langgraph(config: dict) -> str:
    """Export to LangGraph state graph format."""
    system_prompt = config.get("system_prompt", "")
    name = config.get("name", "Agent")
    
    output = f'''"""
LangGraph State Graph for {name}

Generated by AgentConfig.
Reference: Inspired by LangGraph's multi-agent patterns.
"""

from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode

# Define agent state
class AgentState(TypedDict):
    messages: list
    next_action: str

# System prompt
SYSTEM_PROMPT = """
{system_prompt}
"""

def create_agent_graph():
    """Create the agent state graph."""
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    
    # Add edges
    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent",
        should_continue,
        {{"continue": "tools", "end": END}},
    )
    graph.add_edge("tools", "agent")
    
    return graph.compile()

# Example:
# app = create_agent_graph()
# result = app.invoke({{"messages": [("human", "Hello")]}})
'''
    return output


def _export_openai(config: dict) -> str:
    """Export to OpenAI Assistants API format."""
    system_prompt = config.get("system_prompt", "")
    name = config.get("name", "Agent")
    
    output = f'''"""
OpenAI Assistants API Configuration for {name}

Generated by AgentConfig.
To use:
    from openai import OpenAI
    client = OpenAI()
    
    assistant = client.beta.assistants.create(
        name="{name}",
        instructions=SYSTEM_PROMPT,
        model="gpt-4o",
        tools=[...],
    )
"""

SYSTEM_PROMPT = """
{system_prompt}
""".strip()

# Example thread creation:
# thread = client.beta.threads.create()
# message = client.beta.threads.messages.create(
#     thread_id=thread.id,
#     role="user",
#     content="Your message here",
# )
'''
    return output


def _export_a2a(config: dict) -> str:
    """Export to A2A Protocol Agent Card format.

    A2A (Agent-to-Agent) is Google's open protocol for inter-agent
    communication. This exports the agentconfig as a discoverable
    A2A Agent Card (agent.metadata.json).

    Reference: https://a2a-protocol.org
    """
    import json as _json

    name = config.get("name", "Agent")
    system_prompt = config.get("system_prompt", "")
    constraints = config.get("constraints", [])
    metadata = config.get("metadata", {})

    # Derive A2A capabilities from constraints
    skills = []
    for c in constraints:
        ctype = c.get("type", "")
        if ctype == "forbidden_keyword":
            skills.append("content-filter")
        elif ctype == "max_length":
            skills.append("length-enforcement")

    # Extract forbidden topics for description
    forbidden = [
        c.get("params", {}).get("topics", [])
        for c in constraints
        if c.get("type") == "forbidden_topic"
    ]
    flat_forbidden = [t for topics in forbidden for t in topics]

    # Build the A2A Agent Card
    agent_card = {
        "name": name,
        "description": system_prompt[:200].replace("\n", " ").strip() + "...",
        "version": "1.0.0",
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": False,
        },
        "skills": skills if skills else [{"id": "general", "name": "General Agent"}],
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "tags": [metadata.get("domain", "general")],
        "provider": {
            "organization": metadata.get("organization", "agentconfig"),
            "name": "AgentConfig",
            "url": "https://github.com/cdzzy/agentconfig",
        },
        "documentationUrl": "https://github.com/cdzzy/agentconfig",
        "configuration": {
            "systemPrompt": system_prompt,
            "constraints": [
                {
                    "type": c.get("type"),
                    "action": c.get("action"),
                    "params": c.get("params"),
                }
                for c in constraints
            ],
            "maxTurns": config.get("max_turns", 20),
            "forbiddenTopics": flat_forbidden,
        },
    }

    return _json.dumps(agent_card, indent=2, ensure_ascii=False)


def cmd_import_skill(args: argparse.Namespace) -> int:
    """Import an agent configuration from Skill Seekers SKILL.md format."""
    from ..importers.skill_seeker import import_skill
    
    try:
        config = import_skill(
            source=args.source,
            output=args.output,
        )
        
        print(f"\n✅ Successfully imported skill: {config.get('name')}")
        print(f"   Description: {config.get('description', 'N/A')}")
        print(f"   Tools enabled: {len(config.get('tools_enabled', []))}")
        print(f"   Constraints: {len(config.get('constraints', []))}")
        
        if args.output:
            print(f"   Output: {args.output}")
        else:
            print("\n--- Generated Configuration ---")
            import json
            print(json.dumps(config, indent=2, ensure_ascii=False))
        
        return 0
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error importing skill: {e}", file=sys.stderr)
        return 1


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    parser = argparse.ArgumentParser(
        prog="agentconfig",
        description="AgentConfig CLI - Configure AI agents without writing code",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # serve command
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the web UI server",
    )
    serve_parser.add_argument(
        "--config", "-c",
        help="Path to configuration file to load",
    )
    serve_parser.add_argument(
        "--port", "-p",
        type=int,
        default=7860,
        help="Port to run the server on (default: 7860)",
    )
    
    # create command
    create_parser = subparsers.add_parser(
        "create",
        help="Create a new agent configuration",
    )
    create_parser.add_argument(
        "--template", "-t",
        choices=list(get_templates().keys()),
        help="Use a predefined template",
    )
    create_parser.add_argument(
        "--output", "-o",
        help="Output file path (default: print to stdout)",
    )
    
    # validate command
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate an existing configuration file",
    )
    validate_parser.add_argument(
        "--config", "-c",
        required=True,
        help="Path to configuration file to validate",
    )
    
    # list-templates command
    subparsers.add_parser(
        "list-templates",
        help="List available agent templates",
    )
    
    # export command
    export_parser = subparsers.add_parser(
        "export",
        help="Export a configuration to a specific format",
    )
    export_parser.add_argument(
        "--config", "-c",
        required=True,
        help="Path to configuration file to export",
    )
    export_parser.add_argument(
        "--format", "-f",
        choices=["langchain", "langgraph", "openai", "a2a"],
        default="langchain",
        help="Export format (default: langchain)",
    )
    export_parser.add_argument(
        "--output", "-o",
        help="Output file path (default: print to stdout)",
    )
    
    # import-skill command
    import_parser = subparsers.add_parser(
        "import-skill",
        help="Import an agent configuration from Skill Seekers SKILL.md format",
    )
    import_parser.add_argument(
        "--source", "-s",
        required=True,
        help="Path to SKILL.md file or URL to import from",
    )
    import_parser.add_argument(
        "--output", "-o",
        help="Output file path (default: print to stdout)",
    )
    
    return parser


def cli(args: Optional[list] = None) -> int:
    """Main CLI entry point."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    if not parsed_args.command:
        parser.print_help()
        return 0
    
    commands = {
        "serve": cmd_serve,
        "create": cmd_create,
        "validate": cmd_validate,
        "list-templates": cmd_list_templates,
        "export": cmd_export,
        "import-skill": cmd_import_skill,
    }
    
    handler = commands.get(parsed_args.command)
    if handler:
        return handler(parsed_args)
    
    parser.print_help()
    return 0


def main():
    """Entry point for console scripts."""
    sys.exit(cli())


if __name__ == "__main__":
    main()
