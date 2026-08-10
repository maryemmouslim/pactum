import httpx
import pytest
from groq import BadRequestError

from pactum.llm import get_llm, invoke_structured


def test_get_llm_fast_role_uses_instant_model() -> None:
    llm = get_llm("fast")
    assert llm.model_name == "llama-3.1-8b-instant"


def test_get_llm_reasoning_role_uses_versatile_model() -> None:
    llm = get_llm("reasoning")
    assert llm.model_name == "llama-3.3-70b-versatile"


def test_get_llm_default_role_uses_versatile_model() -> None:
    llm = get_llm()
    assert llm.model_name == "llama-3.3-70b-versatile"


def _tool_use_failed_error() -> BadRequestError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(400, request=request, json={"error": {"message": "tool_use_failed"}})
    return BadRequestError("tool_use_failed", response=response, body=None)


class _FlakyLLM:
    def __init__(self, failures_then_result: list[object]) -> None:
        self._calls = iter(failures_then_result)

    def invoke(self, prompt: str) -> object:
        next_value = next(self._calls)
        if isinstance(next_value, Exception):
            raise next_value
        return next_value


def test_invoke_structured_returns_result_on_first_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pactum.llm.time.sleep", lambda seconds: None)
    llm = _FlakyLLM(["ok"])

    assert invoke_structured(llm, "prompt") == "ok"


def test_invoke_structured_retries_after_tool_use_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pactum.llm.time.sleep", lambda seconds: None)
    llm = _FlakyLLM([_tool_use_failed_error(), "ok"])

    assert invoke_structured(llm, "prompt") == "ok"


def test_invoke_structured_gives_up_after_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pactum.llm.time.sleep", lambda seconds: None)
    llm = _FlakyLLM([_tool_use_failed_error(), _tool_use_failed_error(), _tool_use_failed_error()])

    with pytest.raises(BadRequestError):
        invoke_structured(llm, "prompt")
