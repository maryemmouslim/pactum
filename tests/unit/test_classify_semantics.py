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


def _explode_if_called(role: str = "fast") -> FakeLLM:
    raise AssertionError("get_llm should not be called when the PII heuristic is confident")


def test_classify_semantic_type_returns_llm_label_for_non_pii_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_result = SemanticClassification(label="categorical", confidence=0.9)
    monkeypatch.setattr(
        "pactum.tools.classify_semantics.get_llm",
        lambda role="fast": FakeLLM(fake_result),
    )

    result = classify_semantic_type.invoke(
        {
            "column_name": "status",
            "data_type": "TEXT",
            "profile": {"null_percent": 0.0},
            "samples": ["pending", "shipped"],
        }
    )

    assert result == {"label": "categorical", "confidence": 0.9}


def test_classify_semantic_type_flags_email_column_without_calling_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Column name AND sample values both look like email -- the heuristic
    # should classify this locally so the real address never reaches an LLM.
    monkeypatch.setattr("pactum.tools.classify_semantics.get_llm", _explode_if_called)

    result = classify_semantic_type.invoke(
        {
            "column_name": "email",
            "data_type": "TEXT",
            "profile": {"null_percent": 0.0},
            "samples": ["a@example.com", "b@example.com"],
        }
    )

    assert result["label"] == "pii"
    assert result["confidence"] >= 0.9


def test_classify_semantic_type_flags_pii_by_value_shape_even_with_generic_column_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Column name gives no hint, but the values themselves are SSN-shaped --
    # the heuristic should still catch it and skip the LLM call.
    monkeypatch.setattr("pactum.tools.classify_semantics.get_llm", _explode_if_called)

    result = classify_semantic_type.invoke(
        {
            "column_name": "field_7",
            "data_type": "TEXT",
            "profile": {"null_percent": 0.0},
            "samples": ["123-45-6789", "987-65-4321"],
        }
    )

    assert result["label"] == "pii"


def test_classify_semantic_type_flags_pii_by_column_name_even_without_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pactum.tools.classify_semantics.get_llm", _explode_if_called)

    result = classify_semantic_type.invoke(
        {
            "column_name": "credit_card_number",
            "data_type": "TEXT",
            "profile": {"null_percent": 1.0},
            "samples": [],
        }
    )

    assert result["label"] == "pii"
