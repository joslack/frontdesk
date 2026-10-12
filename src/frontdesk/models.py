"""The chat model a worker or the desk agent calls, set up the way refundo's agents set theirs up (refundo, agents/shared.py)."""

import os

from langchain.chat_models import init_chat_model

# The model and effort refundo serves, and the ones its structured agent was measured with. JOBS_MODEL and
# JOBS_MODEL_EFFORT replace them.
MODEL = "fireworks:accounts/fireworks/models/deepseek-v4p1-flash"
EFFORT = "medium"
REQUEST_TIMEOUT = 180  # seconds for one model call; a call that hangs is then retried instead of stalling the run
RETRIES = 8  # per model call; providers limit tokens per minute, and a refused call succeeds a moment later


def chat_model(name: str | None = None, **settings):
    name = name or os.environ.get("JOBS_MODEL", MODEL)
    settings = {"timeout": REQUEST_TIMEOUT, "max_retries": RETRIES} | settings
    if name == os.environ.get("JOBS_MODEL", MODEL) and (effort := os.environ.get("JOBS_MODEL_EFFORT", EFFORT)):
        settings.setdefault("reasoning_effort", effort)
    if name.startswith("anthropic:"):
        # LangChain gives an Anthropic model it does not know a cap of 4,096 output tokens, thinking included.
        settings.setdefault("max_tokens", 32_000)
    if name.startswith("openai:"):
        # Some OpenAI models accept tools only on the Responses API, so every OpenAI model goes through it.
        settings.setdefault("use_responses_api", True)
    return init_chat_model(name, **settings)


def text(content) -> str:
    """A message's content as text, whichever way the model's API shapes it."""
    return content if isinstance(content, str) else "".join(b.get("text", "") for b in content if isinstance(b, dict))
