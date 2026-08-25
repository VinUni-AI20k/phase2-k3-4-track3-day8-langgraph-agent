"""LLM factory helper.

Provides a simple interface to create LLM clients for use in nodes.
Students should use this helper so the lab works with any supported provider.

Usage in nodes:
    from .llm import get_llm
    llm = get_llm()
    response = llm.invoke("Hello")
"""

from __future__ import annotations

import os
from pathlib import Path

# Load .env file from project root
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key, value)


def get_llm(model: str | None = None, temperature: float = 0.0):
    """Create an LLM client from environment configuration.

    Checks for API keys in this order:
    1. GROQ_API_KEY → ChatGroq (fastest, free tier)
    2. GEMINI_API_KEY → ChatGoogleGenerativeAI
    3. OPENAI_API_KEY → ChatOpenAI
    4. ANTHROPIC_API_KEY → ChatAnthropic

    Override model with the `model` parameter or LLM_MODEL env var.
    """
    # GROQ is disabled - API key doesn't have model access
    # if os.getenv("GROQ_API_KEY"):
    #     from langchain_groq import ChatGroq
    #     return ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=os.getenv("GROQ_API_KEY"), temperature=temperature)

    # OpenRouter - supports many models (may require credits)
    # if os.getenv("OPENROUTER_API_KEY"):
    #     from langchain_openai import ChatOpenAI
    #     return ChatOpenAI(
    #         model="anthropic/claude-3-haiku",  # Paid model example
    #         api_key=os.getenv("OPENROUTER_API_KEY"),
    #         base_url="https://openrouter.ai/api/v1",
    #         temperature=temperature,
    #     )

    # Ollama - local models (free, no API needed)
    # Try phi3 first (smaller, faster), fall back to llama3.2
    try:
        from langchain_ollama import ChatOllama
        for model_name in ["phi3:latest", "llama3.2"]:
            try:
                llm = ChatOllama(model=model_name, temperature=temperature)
                # Test if model exists
                llm.invoke("hi")
                return llm
            except Exception:
                continue
    except ImportError:
        pass

    if os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_API_KEY") != "your-gemini-api-key":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError("Install: pip install langchain-google-genai") from exc
        return ChatGoogleGenerativeAI(
            model=model or os.getenv("LLM_MODEL", "gemini-3.6-flash"),
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=temperature,
        )

    if os.getenv("OPENAI_API_KEY"):
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError("Install: pip install langchain-openai") from exc
        return ChatOpenAI(
            model=model or os.getenv("LLM_MODEL", "gpt-4o-mini"),
            temperature=temperature,
        )

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise RuntimeError("Install: pip install langchain-anthropic") from exc
        return ChatAnthropic(
            model=model or os.getenv("LLM_MODEL", "claude-sonnet-4-20250514"),
            temperature=temperature,
        )

    raise RuntimeError(
        "No LLM API key found. Set GROQ_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY in .env\n"
        "See .env.example for configuration."
    )
