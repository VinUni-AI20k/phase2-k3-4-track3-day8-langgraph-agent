"""Day 08 LangGraph agent lab starter."""

from __future__ import annotations

import os
from pathlib import Path

# Load .env from project root if it exists
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

__all__ = ["__version__"]
__version__ = "0.1.0"
