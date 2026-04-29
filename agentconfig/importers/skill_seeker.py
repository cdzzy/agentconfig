"""
Skill Seeker Importer - Import agent configurations from SKILL.md files.

Supports importing from:
- Claude AI Skills (SKILL.md)
- Documentation-based skill definitions
- GitHub repository skill exports

Usage:
    agentconfig import-skill --source <path-or-url>
    agentconfig import-skill --file ./my-skill/SKILL.md --output config.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field


@dataclass
class SkillMetadata:
    """Metadata extracted from a skill file."""
    name: str = ""
    description: str = ""
    author: str = ""
    version: str = "1.0.0"
    tags: List[str] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    guidelines: str = ""


class SkillImporter:
    """
    Import agent configurations from Skill Seekers format (SKILL.md).
    
    Inspired by Skill_Seekers (https://github.com/yusufkaraaslan/Skill_Seekers)
    which converts documentation into Claude AI skills.
    
    This importer reverses the process: takes a SKILL.md and generates
    an AgentConfig that can be used with any agent framework.
    """
    
    # Patterns for parsing SKILL.md sections
    SECTION_PATTERNS = {
        "name": r'^#\s+(.+)$',
        "description": r'\*\*Description[:|]\*\*\s*(.+?)(?:\n|$)',
        "author": r'\*\*Author[:|]\*\*\s*(.+?)(?:\n|$)',
        "version": r'\*\*Version[:|]\*\*\s*(.+?)(?:\n|$)',
        "triggers": r'(?:##?\s*)?[Tt]riggers?[:]?\s*\n((?:\s*[-*]\s*.+\n)+)',
        "examples": r'(?:##?\s*)?[Ee]xamples?[:]?\s*\n((?:\s*[-*]\s*.+\n)+)',
        "constraints": r'(?:##?\s*)?[Cc]onstraints?[:]?\s*\n((?:\s*[-*]\s*.+\n)+)',
        "tools": r'(?:##?\s*)?[Tt]ools?[:]?\s*\n((?:\s*[-*]\s*.+\n)+)',
    }
    
    def import_from_file(self, file_path: str) -> SkillMetadata:
        """
        Import skill metadata from a SKILL.md file.
        
        Args:
            file_path: Path to the SKILL.md file
            
        Returns:
            SkillMetadata with extracted information
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Skill file not found: {file_path}")
        
        content = path.read_text(encoding="utf-8")
        return self._parse_skill_content(content, path.stem)
    
    def import_from_string(self, content: str, name: str = "Imported Skill") -> SkillMetadata:
        """
        Import skill metadata from a string.
        
        Args:
            content: SKILL.md content as string
            name: Fallback name if not found in content
            
        Returns:
            SkillMetadata with extracted information
        """
        return self._parse_skill_content(content, name)
    
    def _parse_skill_content(self, content: str, fallback_name: str) -> SkillMetadata:
        """Parse skill content and extract metadata."""
        metadata = SkillMetadata()
        
        # Extract name (first H1 heading)
        name_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if name_match:
            metadata.name = name_match.group(1).strip()
        else:
            metadata.name = fallback_name
        
        # Extract description
        desc_pattern = r'\*\*Description\*\*:?\s*(.+?)(?:\n\n|\n##|\n#|$)'
        desc_match = re.search(desc_pattern, content, re.DOTALL)
        if desc_match:
            metadata.description = desc_match.group(1).strip()
        
        # Extract author
        author_match = re.search(r'\*\*Author\*\*:?\s*(.+?)(?:\n|$)', content)
        if author_match:
            metadata.author = author_match.group(1).strip()
        
        # Extract version
        version_match = re.search(r'\*\*Version\*\*:?\s*(.+?)(?:\n|$)', content)
        if version_match:
            metadata.version = version_match.group(1).strip()
        
        # Extract tags
        tags_match = re.search(r'\*\*Tags\*\*:?\s*\[([^\]]+)\]', content)
        if tags_match:
            metadata.tags = [t.strip() for t in tags_match.group(1).split(",")]
        
        # Extract list sections
        for section in ["triggers", "examples", "constraints", "tools"]:
            pattern = self.SECTION_PATTERNS.get(section)
            if pattern:
                match = re.search(pattern, content, re.MULTILINE)
                if match:
                    items = re.findall(r'^[-*]\s*(.+)$', match.group(1), re.MULTILINE)
                    setattr(metadata, section, [item.strip() for item in items])
        
        # Extract guidelines (everything after guidelines section)
        guidelines_pattern = r'(?:##?\s*)?[Gg]uidelines?[:]?\s*\n((?:.+(?:\n|$))+'
        guidelines_match = re.search(
            r'(?:##?\s*)?[Gg]uidelines?[:]?\s*\n((?:.+\n)*)',
            content,
            re.DOTALL
        )
        if guidelines_match:
            metadata.guidelines = guidelines_match.group(1).strip()
        
        return metadata
    
    def to_agent_config_dict(self, metadata: SkillMetadata) -> Dict[str, Any]:
        """
        Convert skill metadata to an AgentConfig-compatible dictionary.
        
        Args:
            metadata: Parsed skill metadata
            
        Returns:
            Dictionary ready for AgentConfig
        """
        # Build system prompt from guidelines
        system_prompt_parts = []
        
        if metadata.description:
            system_prompt_parts.append(f"You are a {metadata.name}.")
            system_prompt_parts.append(f"Description: {metadata.description}")
        
        if metadata.guidelines:
            system_prompt_parts.append(f"\nGuidelines:\n{metadata.guidelines}")
        
        if metadata.triggers:
            triggers_text = "\n".join(f"- {t}" for t in metadata.triggers[:5])
            system_prompt_parts.append(f"\nWhen to activate:\n{triggers_text}")
        
        # Build constraints from skill metadata
        constraints = []
        
        if metadata.constraints:
            for i, constraint in enumerate(metadata.constraints[:10]):
                constraints.append({
                    "id": f"skill-constraint-{i}",
                    "type": "forbidden_keyword",
                    "description": f"Skill constraint: {constraint}",
                    "params": {"keywords": constraint.split()},
                    "action": "warn",
                })
        
        # Build output
        return {
            "name": metadata.name,
            "version": metadata.version,
            "description": metadata.description,
            "system_prompt": "\n\n".join(system_prompt_parts),
            "model": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "temperature": 0.7,
                "max_tokens": 2048,
            },
            "constraints": constraints,
            "tools_enabled": metadata.tools[:20] if metadata.tools else [],
            "tools_disabled": [],
            "max_turns": 20,
            "stream": False,
            "log_enabled": True,
            "audit_enabled": True,
            "metadata": {
                "source": "skill-seeker",
                "author": metadata.author,
                "tags": metadata.tags,
                "triggers": metadata.triggers,
                "examples": metadata.examples[:5],
            },
        }


def import_skill(source: str, output: Optional[str] = None) -> Dict[str, Any]:
    """
    Import a skill from file or URL and convert to AgentConfig format.
    
    Args:
        source: Path to SKILL.md file or URL
        output: Optional output file path
        
    Returns:
        The generated configuration dictionary
    """
    importer = SkillImporter()
    
    # Handle URL sources
    if source.startswith(("http://", "https://")):
        try:
            import urllib.request
            with urllib.request.urlopen(source, timeout=10) as response:
                content = response.read().decode("utf-8")
            name = source.split("/")[-1].replace(".md", "") or "WebSkill"
            metadata = importer.import_from_string(content, name)
        except Exception as e:
            raise ValueError(f"Failed to fetch skill from URL: {e}")
    else:
        metadata = importer.import_from_file(source)
    
    config = importer.to_agent_config_dict(metadata)
    
    if output:
        output_path = Path(output)
        output_path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"Configuration saved to: {output_path.absolute()}")
    
    return config
