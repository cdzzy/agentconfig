"""
Example: Import agent configuration from Skill Seekers SKILL.md format.

This example demonstrates how to import a skill created by Skill_Seekers
(https://github.com/yusufkaraaslan/Skill_Seekers) and convert it to
an AgentConfig that can be used with any agent framework.

Usage:
    # From command line
    agentconfig import-skill --source ./my-skill/SKILL.md --output config.json

    # Or use the Python API
    python examples/03_import_skill.py
"""

from agentconfig.importers.skill_seeker import SkillImporter, import_skill


def example_basic_import():
    """Basic example: Import a skill from a file."""
    print("=" * 60)
    print("Example: Basic Skill Import")
    print("=" * 60)
    
    # Example SKILL.md content (simulating a skill file)
    skill_content = """# Coding Assistant Skill

**Description**: A specialized skill for helping developers write better code.
**Author**: Team AI
**Version**: 1.0.0
**Tags**: [coding, development, debugging]

## When to Activate
- User asks for help with code
- User reports a bug or error
- User wants to write a new function
- User asks to review code

## Guidelines
You are a helpful coding assistant. Follow these principles:
1. Always provide working, tested code examples
2. Explain your reasoning clearly
3. Suggest improvements and best practices
4. Point out potential bugs or security issues

## Constraints
- Never write malicious code or security exploits
- Always consider code performance
- Follow language-specific conventions

## Tools
- web-search: Search for documentation
- code-interpreter: Execute code safely
- file-editor: Read and write code files

## Examples
- "Help me write a Python function to sort a list"
- "Debug this code: [code snippet]"
- "Review my pull request"
"""
    
    # Import from string
    importer = SkillImporter()
    metadata = importer.import_from_string(skill_content, "Coding Assistant")
    
    print(f"\n📋 Imported Skill Metadata:")
    print(f"   Name: {metadata.name}")
    print(f"   Description: {metadata.description}")
    print(f"   Author: {metadata.author}")
    print(f"   Version: {metadata.version}")
    print(f"   Tags: {', '.join(metadata.tags)}")
    print(f"   Triggers: {len(metadata.triggers)} items")
    print(f"   Constraints: {len(metadata.constraints)} items")
    print(f"   Tools: {', '.join(metadata.tools)}")
    
    # Convert to AgentConfig
    config = importer.to_agent_config_dict(metadata)
    
    print(f"\n✅ Generated AgentConfig:")
    print(f"   System prompt length: {len(config['system_prompt'])} chars")
    print(f"   Tools enabled: {len(config['tools_enabled'])}")
    print(f"   Constraints: {len(config['constraints'])}")
    
    return config


def example_web_import():
    """Example: Import a skill from a URL."""
    print("\n" + "=" * 60)
    print("Example: Import from URL")
    print("=" * 60)
    
    # Example: Import from GitHub raw URL
    # NOTE: This would require an actual SKILL.md file to exist
    # url = "https://raw.githubusercontent.com/user/repo/main/skills/coding/SKILL.md"
    
    # For demonstration, we show what would happen:
    print("\nTo import from a URL, use:")
    print('  agentconfig import-skill --source "https://example.com/SKILL.md" --output config.json')
    print("\nSupported sources:")
    print("  - Local file: ./my-skill/SKILL.md")
    print("  - GitHub raw: https://raw.githubusercontent.com/.../SKILL.md")
    print("  - Any HTTPS URL pointing to a SKILL.md file")


def example_cli_usage():
    """Show CLI usage examples."""
    print("\n" + "=" * 60)
    print("CLI Usage Examples")
    print("=" * 60)
    
    print("""
# Import from local file
$ agentconfig import-skill --source ./my-agent/SKILL.md --output agent.json

# Import from GitHub repository
$ agentconfig import-skill --source https://raw.githubusercontent.com/user/repo/main/skills/coding/SKILL.md

# Import and print to stdout
$ agentconfig import-skill --source ./skill.md

# Then use the generated config with your agent
$ agentconfig serve --config agent.json
""")


if __name__ == "__main__":
    # Run examples
    config = example_basic_import()
    example_web_import()
    example_cli_usage()
    
    print("\n" + "=" * 60)
    print("✅ All examples completed!")
    print("=" * 60)
