from typing import cast

from pydantic import BaseModel, Field

from pactum.llm import get_llm
from pactum.tools import tool


class SemanticClassification(BaseModel):
    label: str = Field(
        description=(
            "Semantic type: pii, currency, timestamp, identifier, categorical, free_text, or other."
        )
    )
    confidence: float = Field(ge=0.0, le=1.0)


@tool
def classify_semantic_type(
    column_name: str,
    data_type: str,
    profile: dict[str, object],
    samples: list[object],
) -> dict[str, object]:
    """Classify what a column semantically represents using an LLM.

    Args:
        column_name: Name of the column.
        data_type: Source data type of the column.
        profile: Stats for the column (null_percent, distinct_count, min, max).
        samples: A few example values from the column.

    Returns:
        Dict with "label" (semantic type) and "confidence" (0-1).
    """
    llm = get_llm("fast").with_structured_output(SemanticClassification)
    prompt = (
        f"Column name: {column_name}\n"
        f"Data type: {data_type}\n"
        f"Stats: {profile}\n"
        f"Example values: {samples}\n\n"
        "Classify what this column semantically represents. Choose one label: "
        "pii, currency, timestamp, identifier, categorical, free_text, or other."
    )
    result = cast(SemanticClassification, llm.invoke(prompt))
    return result.model_dump()
