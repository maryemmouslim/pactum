from pydantic import BaseModel, Field

from pactum.models import Contract


class ContractGeneratorState(BaseModel):
    dataset_id: str
    columns: dict[str, str] | None = None
    upstream_contracts: list[Contract] = Field(default_factory=list)
    business_context: str | None = None
    samples: list[dict[str, object]] = Field(default_factory=list)
    column_profiles: dict[str, dict[str, object]] = Field(default_factory=dict)
