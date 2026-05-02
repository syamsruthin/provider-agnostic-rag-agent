"""
LLM Abstraction Layer — Provider-Agnostic Inference
=====================================================
Single entry point for all LLM calls in the system.
No other file should directly import a provider SDK (Groq, OpenAI, etc.).

Supported providers (set via LLM_PROVIDER env var):
  - "groq"   : Groq cloud API (default)
  - "openai"  : OpenAI API (or any OpenAI-compatible endpoint via LLM_BASE_URL)
  - "ollama"  : Local Ollama (via OpenAI-compatible API at localhost:11434)

Usage:
    from backend.core.llm import llm_completion

    text = llm_completion(
        messages=[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
        temperature=0,
        max_tokens=512,
    )
"""

from openai import OpenAI

from backend.core.config import LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, LLM_BASE_URL


# ---------------------------------------------------------------------------
# Provider client factory (lazy singleton)
# ---------------------------------------------------------------------------
_client = None


def _get_client() -> OpenAI:
    """
    Return a configured OpenAI-compatible client for the active provider.

    All supported providers (Groq, OpenAI, Ollama) expose an
    OpenAI-compatible chat completions API, so we use the `openai`
    SDK as the universal client.
    """
    global _client
    if _client is not None:
        return _client

    provider = LLM_PROVIDER.lower()

    if provider == "groq":
        _client = OpenAI(
            api_key=LLM_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
    elif provider == "openai":
        kwargs = {"api_key": LLM_API_KEY}
        if LLM_BASE_URL:
            kwargs["base_url"] = LLM_BASE_URL
        _client = OpenAI(**kwargs)
    elif provider == "ollama":
        _client = OpenAI(
            api_key="ollama",  # Ollama doesn't need a real key
            base_url=LLM_BASE_URL or "http://localhost:11434/v1",
        )
    else:
        # Generic OpenAI-compatible endpoint
        _client = OpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_BASE_URL or "https://api.openai.com/v1",
        )

    return _client


# ---------------------------------------------------------------------------
# Public API — the only function any module should call
# ---------------------------------------------------------------------------

def llm_completion(
    messages: list[dict],
    *,
    temperature: float = 0,
    max_tokens: int = 512,
    model: str | None = None,
) -> str:
    """
    Send a chat completion request to the configured LLM provider.

    Args:
        messages: List of {"role": ..., "content": ...} dicts.
        temperature: Sampling temperature (0 = deterministic).
        max_tokens: Maximum tokens in the response.
        model: Override the default model. If None, uses LLM_MODEL from config.

    Returns:
        The assistant's response text (stripped).
    """
    client = _get_client()
    response = client.chat.completions.create(
        model=model or LLM_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def reset_client() -> None:
    """Reset the cached client (useful for testing or provider switching)."""
    global _client
    _client = None
