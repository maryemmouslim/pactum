import time
from typing import Protocol

from groq import BadRequestError
from langchain_groq import ChatGroq
from pydantic import SecretStr

from pactum.settings import settings

_MAX_RETRIES = 2
_RETRY_DELAY_SECONDS = 0.5


def get_llm(role: str = "reasoning") -> ChatGroq:
    """Return a configured Groq model for a given agent role.

    role: "reasoning" (causal agent, contract gen) or "fast" (classification, critique).
    """
    model = "llama-3.1-8b-instant" if role == "fast" else "llama-3.3-70b-versatile"
    return ChatGroq(
        model=model,
        api_key=SecretStr(settings.groq_api_key),
        temperature=0.1,
    )


class _StructuredLLM(Protocol):
    def invoke(self, prompt: str, /) -> object: ...


def invoke_structured(llm: _StructuredLLM, prompt: str) -> object:
    """Invoke a .with_structured_output(...) LLM, retrying on Groq tool-call flakiness.

    Groq's models occasionally emit a malformed function call as plain text
    instead of a real tool call -- the API rejects it with
    BadRequestError(code="tool_use_failed"). This is sampling noise from the
    model, not a problem with the prompt, and simply retrying the identical
    call usually succeeds.
    """
    last_error: BadRequestError | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            return llm.invoke(prompt)
        except BadRequestError as exc:
            last_error = exc
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY_SECONDS)
    assert last_error is not None
    raise last_error
