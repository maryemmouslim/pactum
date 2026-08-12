import pytest

from pactum.eval.judge import JudgeVerdict, judge_hypothesis


class FakeStructuredLLM:
    def __init__(self, result: object) -> None:
        self._result = result

    def invoke(self, prompt: str) -> object:
        return self._result


class FakeLLM:
    def __init__(self, result: object) -> None:
        self._result = result

    def with_structured_output(self, schema: object) -> FakeStructuredLLM:
        return FakeStructuredLLM(self._result)


def test_judge_hypothesis_returns_the_llms_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_verdict = JudgeVerdict(correct=True, reasoning="Both describe the same root cause.")
    monkeypatch.setattr("pactum.eval.judge.get_llm", lambda role="reasoning": FakeLLM(fake_verdict))

    verdict = judge_hypothesis(
        expected_cause="A new column was added upstream.",
        actual_hypothesis="It looks like a new column appeared that isn't in the contract.",
    )

    assert verdict.correct is True
    assert verdict.reasoning == "Both describe the same root cause."


def test_judge_hypothesis_can_return_false(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_verdict = JudgeVerdict(correct=False, reasoning="Points at an unrelated cause.")
    monkeypatch.setattr("pactum.eval.judge.get_llm", lambda role="reasoning": FakeLLM(fake_verdict))

    verdict = judge_hypothesis(
        expected_cause="A new column was added upstream.",
        actual_hypothesis="The freshness SLA was violated because ingestion stalled.",
    )

    assert verdict.correct is False
