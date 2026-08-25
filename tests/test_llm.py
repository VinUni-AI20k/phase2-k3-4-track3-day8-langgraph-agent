"""LLM configuration tests."""

import sys
from pathlib import Path
from types import ModuleType

from langgraph_agent_lab import llm


def test_get_llm_loads_repository_env_before_provider_lookup(monkeypatch, tmp_path: Path) -> None:
    """Given repository .env, get_llm selects Gemini without logging its key."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(llm, "REPOSITORY_ENV_FILE", tmp_path / ".env")
    (tmp_path / ".env").write_text("GEMINI_API_KEY=test-gemini-key\nLLM_MODEL=test-model\n")

    class FakeGemini:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    fake_module = ModuleType("langchain_google_genai", doc=None)
    fake_module.__dict__["ChatGoogleGenerativeAI"] = FakeGemini
    monkeypatch.setitem(sys.modules, "langchain_google_genai", fake_module)

    result = llm.get_llm()

    assert isinstance(result, FakeGemini)
    assert result.kwargs["model"] == "test-model"
    assert result.kwargs["google_api_key"] == "test-gemini-key"
