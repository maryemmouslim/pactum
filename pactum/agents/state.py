from pydantic import BaseModel, Field

from pactum.models import Contract


class ContractGeneratorState(BaseModel):
    dataset_id: str
    columns: dict[str, str] | None = None
    upstream_contracts: list[Contract] = Field(default_factory=list)
    business_context: str | None = None
    samples: list[dict[str, object]] = Field(default_factory=list)
    column_profiles: dict[str, dict[str, object]] = Field(default_factory=dict)
    semantic_classifications: dict[str, dict[str, object]] = Field(default_factory=dict)
    draft_yaml: str | None = None
    revision_count: int = 0
    critique_approved: bool | None = None
    critique_feedback: str | None = None
    written_contract: Contract | None = None
