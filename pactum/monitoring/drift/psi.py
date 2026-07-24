from typing import SupportsFloat, cast

import numpy as np

from pactum.monitoring.drift.protocol import DriftDetector, DriftResult

_EPSILON = 1e-6
_DRIFT_THRESHOLD = 0.25


class PSIDetector(DriftDetector):
    supported_types = {"numeric"}

    def detect(self, reference: list[object], current: list[object]) -> DriftResult:
        ref = np.array([float(cast(SupportsFloat, v)) for v in reference if v is not None])
        cur = np.array([float(cast(SupportsFloat, v)) for v in current if v is not None])

        bin_edges = np.quantile(ref, np.linspace(0, 1, 11))
        bin_edges[0] = -np.inf
        bin_edges[-1] = np.inf

        ref_counts, _ = np.histogram(ref, bins=bin_edges)
        cur_counts, _ = np.histogram(cur, bins=bin_edges)

        ref_percents = ref_counts / len(ref) + _EPSILON
        cur_percents = cur_counts / len(cur) + _EPSILON

        psi = float(np.sum((cur_percents - ref_percents) * np.log(cur_percents / ref_percents)))

        return DriftResult(
            drifted=psi > _DRIFT_THRESHOLD,
            score=psi,
            method="psi",
            details={"bin_edges": bin_edges.tolist()},
        )
