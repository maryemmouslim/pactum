import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pactum.models import (
    Contract,
    ContractReview,
    Explanation,
    Hypothesis,
    Incident,
    LineageEdge,
    RefinementProposal,
)


def test_contract_json_round_trip() -> None:
    contract = Contract(
        id=uuid.uuid4(),
        dataset_id="orders",
        version=1,
        yaml="apiVersion: v3",
        status="draft",
        parent_version_id=None,
        created_at=datetime.now(UTC),
        created_by="test",
    )

    restored = Contract.model_validate_json(contract.model_dump_json())

    assert restored == contract


def test_contract_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        Contract(
            id=uuid.uuid4(),
            dataset_id="orders",
            version=1,
            yaml="apiVersion: v3",
            status="not_a_real_status",  # type: ignore[arg-type]
            created_at=datetime.now(UTC),
            created_by="test",
        )


def test_incident_json_round_trip() -> None:
    incident = Incident(
        id=uuid.uuid4(),
        dataset_id="orders",
        detected_at=datetime.now(UTC),
        kind="drift",
        severity="high",
        signature="abc123",
        payload={"score": 0.5},
        contract_version_id=uuid.uuid4(),
        check_type="psi",
        column_name="amount",
    )

    restored = Incident.model_validate_json(incident.model_dump_json())

    assert restored == incident


def test_incident_rejects_invalid_kind() -> None:
    with pytest.raises(ValidationError):
        Incident(
            id=uuid.uuid4(),
            dataset_id="orders",
            detected_at=datetime.now(UTC),
            kind="not_a_real_kind",  # type: ignore[arg-type]
            severity="high",
            signature="abc123",
            payload={},
            contract_version_id=uuid.uuid4(),
            check_type="psi",
        )


def test_hypothesis_confidence_must_be_between_zero_and_one() -> None:
    Hypothesis(description="a cause", confidence=0.0)
    Hypothesis(description="a cause", confidence=1.0)

    with pytest.raises(ValidationError):
        Hypothesis(description="a cause", confidence=1.5)

    with pytest.raises(ValidationError):
        Hypothesis(description="a cause", confidence=-0.1)


def test_explanation_json_round_trip() -> None:
    explanation = Explanation(
        id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        hypotheses=[Hypothesis(description="a cause", confidence=0.8)],
        reasoning_trace=[{"tool": "get_lineage", "result": "ok"}],
        created_at=datetime.now(UTC),
    )

    restored = Explanation.model_validate_json(explanation.model_dump_json())

    assert restored == explanation


def test_refinement_proposal_json_round_trip() -> None:
    proposal = RefinementProposal(
        id=uuid.uuid4(),
        incident_id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        kind="tightening",
        proposed_yaml="apiVersion: v3",
        status="pending",
        created_at=datetime.now(UTC),
    )

    restored = RefinementProposal.model_validate_json(proposal.model_dump_json())

    assert restored == proposal


def test_refinement_proposal_rejects_invalid_kind() -> None:
    with pytest.raises(ValidationError):
        RefinementProposal(
            id=uuid.uuid4(),
            incident_id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            kind="not_a_real_kind",  # type: ignore[arg-type]
            proposed_yaml="apiVersion: v3",
            status="pending",
            created_at=datetime.now(UTC),
        )


def test_contract_review_json_round_trip() -> None:
    review = ContractReview(
        id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        decision="rejected",
        reason="Order ID isn't actually unique in this dataset",
        reviewed_by="ui-user",
        reviewed_at=datetime.now(UTC),
    )

    restored = ContractReview.model_validate_json(review.model_dump_json())

    assert restored == review


def test_contract_review_reason_is_optional() -> None:
    review = ContractReview(
        id=uuid.uuid4(),
        contract_id=uuid.uuid4(),
        decision="approved",
        reviewed_by="ui-user",
        reviewed_at=datetime.now(UTC),
    )

    assert review.reason is None


def test_contract_review_rejects_invalid_decision() -> None:
    with pytest.raises(ValidationError):
        ContractReview(
            id=uuid.uuid4(),
            contract_id=uuid.uuid4(),
            decision="maybe",  # type: ignore[arg-type]
            reviewed_by="ui-user",
            reviewed_at=datetime.now(UTC),
        )


def test_lineage_edge_json_round_trip() -> None:
    edge = LineageEdge(upstream_dataset_id="raw_orders", downstream_dataset_id="orders")

    restored = LineageEdge.model_validate_json(edge.model_dump_json())

    assert restored == edge
