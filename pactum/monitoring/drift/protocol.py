from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class DriftResult(BaseModel):
    drifted: bool
    score: float
    method: str
    details: dict[str, object] = Field(default_factory=dict)


class DriftDetector(ABC):
    supported_types: set[str] = set()

    @abstractmethod
    def detect(self, reference: list[object], current: list[object]) -> DriftResult:
        """Compare a reference sample and a current sample, return a DriftResult."""
