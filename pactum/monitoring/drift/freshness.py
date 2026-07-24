from datetime import datetime
from typing import cast

from pactum.monitoring.drift.protocol import DriftDetector, DriftResult, insufficient_data_result

_EPSILON = 1e-6
_DRIFT_RATIO_THRESHOLD = 2.0
_MIN_SAMPLE_SIZE = 2


class FreshnessDetector(DriftDetector):
    supported_types = {"timestamp"}

    def detect(self, reference: list[object], current: list[object]) -> DriftResult:
        ref_timestamps = [cast(datetime, ts) for ts in reference if ts is not None]
        cur_timestamps = [cast(datetime, ts) for ts in current if ts is not None]

        if len(ref_timestamps) < _MIN_SAMPLE_SIZE or len(cur_timestamps) < _MIN_SAMPLE_SIZE:
            return insufficient_data_result(
                "freshness_delta", "reference or current window has fewer than 2 timestamps"
            )

        ref_lag = self._average_gap_seconds(ref_timestamps)
        cur_lag = self._average_gap_seconds(cur_timestamps)

        # Epsilon avoids a literal division by zero when a window has zero
        # variance in arrival gaps (e.g. a burst of identical timestamps),
        # instead of the old behavior of reporting infinite, misleading drift.
        ratio = (cur_lag + _EPSILON) / (ref_lag + _EPSILON)

        return DriftResult(
            drifted=ratio > _DRIFT_RATIO_THRESHOLD,
            score=ratio,
            method="freshness_delta",
            details={"reference_avg_gap_seconds": ref_lag, "current_avg_gap_seconds": cur_lag},
        )

    @staticmethod
    def _average_gap_seconds(timestamps: list[datetime]) -> float:
        parsed = sorted(timestamps)
        gaps = [(parsed[i + 1] - parsed[i]).total_seconds() for i in range(len(parsed) - 1)]
        return sum(gaps) / len(gaps)
