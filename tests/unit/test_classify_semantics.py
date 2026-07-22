import pytest

from pactum.tools.classify_semantics import SemanticClassification, classify_semantic_type


class FakeStructuredLLM:
    def __init__(self, result: SemanticClassification) -> None:
        self._result = result

    def invoke(self, prompt: str) -> SemanticClassification:
        return self._result


class FakeLLM:
    def __init__(self, result: SemanticClassification) -> None:
        self._result = result

    def with_structured_output(self, schema: object) -> FakeStructuredLLM:
        return FakeStructuredLLM(self._result)


def test_classify_semantic_type_returns_llm_label(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_result = SemanticClassification(label="pii", confidence=0.9)
    monkeypatch.setattr(
        "pactum.tools.classify_semantics.get_llm",
        lambda role="fast": FakeLLM(fake_result),
    )

    result = classify_semantic_type.invoke(
        {
            "column_name": "email",
            "data_type": "TEXT",
            "profile": {"null_percent": 0.0},
            "samples": ["a@example.com"],
        }
    )

    assert result == {"label": "pii", "confidence": 0.9}
