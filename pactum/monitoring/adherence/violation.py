from pydantic import BaseModel, Field


class Violation(BaseModel):
    passed: bool
    check_type: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)
