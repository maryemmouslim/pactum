from typing import SupportsFloat, cast

from scipy.stats import ks_2samp

from pactum.monitoring.drift.protocol import DriftDetector, DriftResult, insufficient_data_result

_SIGNIFICANCE_LEVEL = 0.05
_MIN_SAMPLE_SIZE = 2


class KSDetector(DriftDetector):
    supported_types = {"numeric"}

    def detect(self, reference: list[object], current: list[object]) -> DriftResult:
        ref = [float(cast(SupportsFloat, v)) for v in reference if v is not None]
        cur = [float(cast(SupportsFloat, v)) for v in current if v is not None]

        if len(ref) < _MIN_SAMPLE_SIZE or len(cur) < _MIN_SAMPLE_SIZE:
            return insufficient_data_result(
                "ks", "reference or current window has fewer than 2 non-null values"
            )

        test_result = ks_2samp(ref, cur)
        p_value = float(test_result.pvalue)
        statistic = float(test_result.statistic)

        return DriftResult(
            drifted=p_value < _SIGNIFICANCE_LEVEL,
            score=statistic,
            method="ks",
            details={"p_value": p_value},
        )
