import uuid
from datetime import UTC, datetime

import pytest

from pactum.agents.contract_generator import (
    CritiqueResult,
    _build_draft_prompt,
    build_contract_generator_graph,
    classify_semantics,
    draft_contract,
    profile_columns,
    route_after_critique,
    self_critique,
    understand_source,
    write_contract,
)
from pactum.agents.state import ContractGeneratorState
from pactum.lineage.graph import LineageGraph
from pactum.models import Contract
from pactum.sources import registry as source_registry
from pactum.sources.business_context import register_business_context
from pactum.tools.classify_semantics import SemanticClassification


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


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeDraftLLM:
    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, prompt: str) -> FakeMessage:
        return FakeMessage(self._content)


class FakeCritiqueStructuredLLM:
    def __init__(self, result: CritiqueResult) -> None:
        self._result = result

    def invoke(self, prompt: str) -> CritiqueResult:
        return self._result


class FakeCritiqueLLM:
    def __init__(self, result: CritiqueResult) -> None:
        self._result = result

    def with_structured_output(self, schema: object) -> FakeCritiqueStructuredLLM:
        return FakeCritiqueStructuredLLM(self._result)


class FakeAdapter:
    def list_datasets(self) -> list[str]:
        return ["orders"]

    def get_schema(self, dataset: str) -> dict[str, str]:
        return {"order_id": "TEXT"}

    def sample(self, dataset: str, n: int = 10) -> list[tuple[object, ...]]:
        return [("o1",), ("o2",)]


@pytest.fixture(autouse=True)
def _clear_registries() -> None:
    source_registry._adapters.clear()
    from pactum.sources import business_context

    business_context._context.clear()


def test_understand_source_populates_state(monkeypatch: pytest.MonkeyPatch) -> None:
    source_registry.register_source(FakeAdapter())
    register_business_context("orders", "Customer purchase events.")
    monkeypatch.setattr("pactum.tools.understand_source.load_graph", lambda: LineageGraph())

    result = understand_source(ContractGeneratorState(dataset_id="orders"))

    assert result.columns == {"order_id": "TEXT"}
    assert result.upstream_contracts == []
    assert result.business_context == "Customer purchase events."


def test_profile_columns_populates_state() -> None:
    source_registry.register_source(FakeAdapter())

    result = profile_columns(ContractGeneratorState(dataset_id="orders"))

    assert result.samples == [{"order_id": "o1"}, {"order_id": "o2"}]
    assert set(result.column_profiles.keys()) == {"order_id"}


def test_classify_semantics_populates_state(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_result = SemanticClassification(label="identifier", confidence=0.95)
    monkeypatch.setattr(
        "pactum.tools.classify_semantics.get_llm",
        lambda role="fast": FakeLLM(fake_result),
    )

    state = ContractGeneratorState(
        dataset_id="orders",
        columns={"order_id": "TEXT"},
        samples=[{"order_id": "o1"}, {"order_id": "o2"}],
        column_profiles={"order_id": {"null_percent": 0.0}},
    )

    result = classify_semantics(state)

    assert result.semantic_classifications == {
        "order_id": {"label": "identifier", "confidence": 0.95}
    }


def test_draft_contract_populates_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "pactum.agents.contract_generator.get_llm",
        lambda role="reasoning": FakeDraftLLM("apiVersion: v3\nkind: DataContract"),
    )

    state = ContractGeneratorState(
        dataset_id="orders",
        columns={"order_id": "TEXT"},
        semantic_classifications={"order_id": {"label": "identifier", "confidence": 0.95}},
        column_profiles={"order_id": {"null_percent": 0.0}},
    )

    result = draft_contract(state)

    assert result.draft_yaml == "apiVersion: v3\nkind: DataContract"


def test_build_draft_prompt_includes_feedback_after_rejection() -> None:
    state = ContractGeneratorState(
        dataset_id="orders",
        columns={"order_id": "TEXT"},
        critique_feedback="Missing a freshness SLA.",
    )

    prompt = _build_draft_prompt(state)

    assert "Missing a freshness SLA." in prompt
    assert "rejected during review" in prompt


def test_build_draft_prompt_omits_feedback_section_on_first_attempt() -> None:
    state = ContractGeneratorState(dataset_id="orders", columns={"order_id": "TEXT"})

    prompt = _build_draft_prompt(state)

    assert "rejected during review" not in prompt


def test_self_critique_approved_does_not_bump_revision_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_result = CritiqueResult(approved=True, feedback="")
    monkeypatch.setattr(
        "pactum.agents.contract_generator.get_llm",
        lambda role="fast": FakeCritiqueLLM(fake_result),
    )

    state = ContractGeneratorState(dataset_id="orders", draft_yaml="apiVersion: v3")
    result = self_critique(state)

    assert result.critique_approved is True
    assert result.revision_count == 0


def test_self_critique_not_approved_bumps_revision_count_and_saves_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_result = CritiqueResult(approved=False, feedback="Missing freshness SLA.")
    monkeypatch.setattr(
        "pactum.agents.contract_generator.get_llm",
        lambda role="fast": FakeCritiqueLLM(fake_result),
    )

    state = ContractGeneratorState(dataset_id="orders", draft_yaml="apiVersion: v3")
    result = self_critique(state)

    assert result.critique_approved is False
    assert result.critique_feedback == "Missing freshness SLA."
    assert result.revision_count == 1


def test_route_after_critique_goes_to_write_when_approved() -> None:
    state = ContractGeneratorState(dataset_id="orders", critique_approved=True, revision_count=0)
    assert route_after_critique(state) == "write_contract"


def test_route_after_critique_goes_to_draft_when_not_approved_and_under_limit() -> None:
    state = ContractGeneratorState(dataset_id="orders", critique_approved=False, revision_count=1)
    assert route_after_critique(state) == "draft_contract"


def test_route_after_critique_goes_to_write_when_revision_limit_reached() -> None:
    state = ContractGeneratorState(dataset_id="orders", critique_approved=False, revision_count=2)
    assert route_after_critique(state) == "write_contract"


def test_write_contract_delegates_version_allocation_to_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # write_contract no longer computes the version/parent itself -- that's
    # the registry's job now (see contract_registry.create_version), which
    # allocates it atomically. This test only checks the wiring: the right
    # arguments get passed, and the registry's result is stored as-is.
    fake_contract = Contract(
        id=uuid.uuid4(),
        dataset_id="orders",
        version=1,
        yaml="apiVersion: v3",
        status="draft",
        parent_version_id=None,
        created_at=datetime.now(UTC),
        created_by="contract-generator-agent",
    )
    captured: dict[str, object] = {}

    def fake_create_version(
        dataset_id: str, yaml: str, created_by: str, status: str = "draft"
    ) -> Contract:
        captured.update(dataset_id=dataset_id, yaml=yaml, created_by=created_by)
        return fake_contract

    monkeypatch.setattr("pactum.agents.contract_generator.create_version", fake_create_version)

    state = ContractGeneratorState(dataset_id="orders", draft_yaml="apiVersion: v3")
    result = write_contract(state)

    assert result.written_contract is fake_contract
    assert captured == {
        "dataset_id": "orders",
        "yaml": "apiVersion: v3",
        "created_by": "contract-generator-agent",
    }


def test_full_graph_runs_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    source_registry.register_source(FakeAdapter())
    monkeypatch.setattr("pactum.tools.understand_source.load_graph", lambda: LineageGraph())
    monkeypatch.setattr(
        "pactum.tools.classify_semantics.get_llm",
        lambda role="fast": FakeLLM(SemanticClassification(label="identifier", confidence=0.9)),
    )

    def fake_create_version(
        dataset_id: str, yaml: str, created_by: str, status: str = "draft"
    ) -> Contract:
        return Contract(
            id=uuid.uuid4(),
            dataset_id=dataset_id,
            version=1,
            yaml=yaml,
            status=status,
            parent_version_id=None,
            created_at=datetime.now(UTC),
            created_by=created_by,
        )

    monkeypatch.setattr("pactum.agents.contract_generator.create_version", fake_create_version)

    draft_then_critique_llms = iter(
        [
            FakeDraftLLM("apiVersion: v3\nkind: DataContract"),
            FakeCritiqueLLM(CritiqueResult(approved=True, feedback="")),
        ]
    )
    monkeypatch.setattr(
        "pactum.agents.contract_generator.get_llm",
        lambda role="reasoning": next(draft_then_critique_llms),
    )

    app = build_contract_generator_graph()
    result = app.invoke(ContractGeneratorState(dataset_id="orders"))

    assert result["written_contract"].status == "draft"
    assert result["written_contract"].version == 1
    assert result["draft_yaml"] == "apiVersion: v3\nkind: DataContract"
    assert result["critique_approved"] is True
