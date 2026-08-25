"""LLM factory helper.

Provides a simple interface to create LLM clients for use in nodes.
Students should use this helper so the lab works with any supported provider.

Usage in nodes:
    from .llm import get_llm
    llm = get_llm()
    response = llm.invoke("Hello")
"""

import os
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    load_dotenv()
except ImportError:
    pass


def get_llm(model: str | None = None, temperature: float = 0.0) -> Any:  # noqa: ANN401
    """Create an LLM client from environment configuration."""
    if os.getenv("GEMINI_API_KEY"):
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError("Install: pip install langchain-google-genai") from exc
        chosen_model = model or os.getenv("LLM_MODEL") or "gemini-2.5-flash"
        return ChatGoogleGenerativeAI(
            model=chosen_model,
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=temperature,
        )

    if os.getenv("OPENAI_API_KEY"):
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError("Install: pip install langchain-openai") from exc
        chosen_model = model or os.getenv("LLM_MODEL") or "gpt-4o-mini"
        return ChatOpenAI(
            model=chosen_model,
            temperature=temperature,
        )

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise RuntimeError("Install: pip install langchain-anthropic") from exc
        chosen_model = model or os.getenv("LLM_MODEL") or "claude-sonnet-4-20250514"
        return ChatAnthropic(  # type: ignore[call-arg]
            model_name=chosen_model,
            temperature=temperature,
        )

    raise RuntimeError(
        "No LLM API key found. Set GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY in .env\n"
        "See .env.example for configuration."
    )
