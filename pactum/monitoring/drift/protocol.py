from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class DriftResult(BaseModel):
    drifted: bool
    score: float
    method: str
    details: dict[str, object] = Field(default_factory=dict)
    insufficient_data: bool = False


class DriftDetector(ABC):
    supported_types: set[str] = set()

    @abstractmethod
    def detect(self, reference: list[object], current: list[object]) -> DriftResult:
        """Compare a reference sample and a current sample, return a DriftResult."""


def insufficient_data_result(method: str, reason: str) -> DriftResult:
    """Build a DriftResult signaling the comparison could not be statistically evaluated.

    Used instead of crashing or returning a misleading score (e.g. NaN or
    infinity) when a window has too little data to compare.
    """
    return DriftResult(
        drifted=False,
        score=0.0,
        method=method,
        insufficient_data=True,
        details={"reason": reason},
    )
