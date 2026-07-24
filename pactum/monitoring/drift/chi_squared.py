from collections import Counter

from scipy.stats import chi2_contingency

from pactum.monitoring.drift.protocol import DriftDetector, DriftResult, insufficient_data_result

_SIGNIFICANCE_LEVEL = 0.05


class ChiSquaredDetector(DriftDetector):
    supported_types = {"categorical"}

    def detect(self, reference: list[object], current: list[object]) -> DriftResult:
        ref = [v for v in reference if v is not None]
        cur = [v for v in current if v is not None]

        if not ref or not cur:
            return insufficient_data_result(
                "chi_squared", "reference or current window has no non-null values"
            )

        categories = sorted({str(v) for v in ref} | {str(v) for v in cur})
        ref_counts = Counter(str(v) for v in ref)
        cur_counts = Counter(str(v) for v in cur)

        table = [
            [ref_counts.get(category, 0) for category in categories],
            [cur_counts.get(category, 0) for category in categories],
        ]

        result = chi2_contingency(table)

        return DriftResult(
            drifted=bool(result.pvalue < _SIGNIFICANCE_LEVEL),
            score=float(result.statistic),
            method="chi_squared",
            details={"p_value": float(result.pvalue), "categories": categories},
        )
