import yaml
from pydantic import BaseModel, Field


class ColumnRule(BaseModel):
    name: str
    data_type: str
    semantic_type: str = Field(
        description="pii, currency, timestamp, identifier, categorical, free_text, or other"
    )
    sensitivity: bool = Field(
        default=False, description="True if this column must never be sampled raw to an LLM."
    )
    nullable: bool = True
    unique: bool = False
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[str] | None = None
    regex_pattern: str | None = None
    references_dataset: str | None = Field(
        default=None, description="If this is a foreign key, the dataset it references."
    )
    references_column: str | None = Field(
        default=None, description="If this is a foreign key, the column it references."
    )


class ParsedContract(BaseModel):
    dataset_id: str
    columns: list[ColumnRule]
    freshness_sla_seconds: float | None = Field(
        default=None, description="Maximum allowed age, in seconds, of the newest record."
    )
    completeness_sla: float | None = Field(
        default=None, description="Minimum required fraction of non-null values, e.g. 0.95."
    )

    def get_column(self, name: str) -> ColumnRule | None:
        return next((column for column in self.columns if column.name == name), None)


def render_contract_yaml(contract: ParsedContract) -> str:
    """Render a ParsedContract into YAML text for storage and human review."""
    return yaml.dump(contract.model_dump(), sort_keys=False)


def parse_contract_yaml(yaml_text: str) -> ParsedContract:
    """Parse a contract's stored YAML back into structured, enforceable rules.

    This only works reliably because we control exactly how the YAML gets
    written (render_contract_yaml) -- it is not a general-purpose parser for
    arbitrary hand-written ODCS YAML.
    """
    data = yaml.safe_load(yaml_text)
    return ParsedContract.model_validate(data)
