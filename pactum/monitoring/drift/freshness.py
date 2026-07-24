from datetime import datetime
from typing import cast

from pactum.monitoring.drift.protocol import DriftDetector, DriftResult

_DRIFT_RATIO_THRESHOLD = 2.0


class FreshnessDetector(DriftDetector):
    supported_types = {"timestamp"}

    def detect(self, reference: list[object], current: list[object]) -> DriftResult:
        ref_lag = self._average_gap_seconds(reference)
        cur_lag = self._average_gap_seconds(current)

        ratio = cur_lag / ref_lag if ref_lag > 0 else float("inf")

        return DriftResult(
            drifted=ratio > _DRIFT_RATIO_THRESHOLD,
            score=ratio,
            method="freshness_delta",
            details={"reference_avg_gap_seconds": ref_lag, "current_avg_gap_seconds": cur_lag},
        )

    @staticmethod
    def _average_gap_seconds(timestamps: list[object]) -> float:
        parsed = sorted(cast(datetime, ts) for ts in timestamps if ts is not None)
        if len(parsed) < 2:
            return 0.0
        gaps = [(parsed[i + 1] - parsed[i]).total_seconds() for i in range(len(parsed) - 1)]
        return sum(gaps) / len(gaps)
