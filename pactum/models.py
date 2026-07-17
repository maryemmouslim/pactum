from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Contract(BaseModel):
    id: UUID
    dataset_id: str
    version: int
    yaml: str
    status: Literal["draft", "active", "deprecated"]
    parent_version_id: UUID | None = None
    created_at: datetime
    created_by: str


class Incident(BaseModel):
    id: UUID
    dataset_id: str
    detected_at: datetime
    kind: Literal["drift", "violation"]
    severity: Literal["low", "medium", "high"]
    signature: str
    payload: dict
    contract_version: str


class Hypothesis(BaseModel):
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_action: str | None = None
    related_incident_id: UUID | None = None


class Explanation(BaseModel):
    id: UUID
    incident_id: UUID
    hypotheses: list[Hypothesis]
    reasoning_trace: list[dict]
    created_at: datetime


class RefinementProposal(BaseModel):
    id: UUID
    incident_id: UUID
    contract_id: UUID
    kind: Literal["relaxation", "tightening", "new_rule", "scoping"]
    proposed_yaml: str
    status: Literal["pending", "accepted", "rejected"]
    created_at: datetime


class LineageEdge(BaseModel):
    upstream_dataset_id: str
    downstream_dataset_id: str
