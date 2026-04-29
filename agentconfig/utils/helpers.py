"""Shared utility helpers."""

import json
import re


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return text.strip('-')


def truncate(text: str, max_len: int = 120, suffix: str = "…") -> str:
    """Truncate text to max_len characters."""
    if len(text) <= max_len:
        return text
    return text[:max_len - len(suffix)] + suffix


def safe_json(obj) -> str:
    """Serialize to JSON, handling non-serializable objects."""
    def default(o):
        if hasattr(o, '__dict__'):
            return o.__dict__
        return str(o)
    return json.dumps(obj, default=default, ensure_ascii=False)
