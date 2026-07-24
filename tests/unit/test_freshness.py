from datetime import datetime, timedelta

import pytest

from pactum.monitoring.drift.freshness import FreshnessDetector


def test_freshness_detects_no_drift_for_same_arrival_cadence() -> None:
    detector = FreshnessDetector()
    start = datetime(2026, 1, 1)
    reference = [start + timedelta(minutes=i) for i in range(60)]
    current = [start + timedelta(days=1, minutes=i) for i in range(60)]

    result = detector.detect(reference, current)

    assert result.method == "freshness_delta"
    assert result.score == 1.0
    assert result.drifted is False


def test_freshness_detects_drift_when_data_arrives_slower() -> None:
    detector = FreshnessDetector()
    start = datetime(2026, 1, 1)
    reference = [start + timedelta(minutes=i) for i in range(60)]
    current = [start + timedelta(days=1, minutes=i * 10) for i in range(60)]

    result = detector.detect(reference, current)

    assert result.drifted is True
    assert result.score == pytest.approx(10.0)


def test_freshness_returns_insufficient_data_for_single_timestamp() -> None:
    t = datetime(2026, 1, 1)
    result = FreshnessDetector().detect([t], [t, t])

    assert result.insufficient_data is True
    assert result.drifted is False


def test_freshness_no_drift_for_identical_zero_variance_windows() -> None:
    # Both windows are bursts of identical timestamps (zero gap) -- this
    # used to compute ratio = inf and report drifted=True, which was wrong:
    # nothing actually changed between reference and current.
    t = datetime(2026, 1, 1)
    result = FreshnessDetector().detect([t, t], [t, t])

    assert result.insufficient_data is False
    assert result.score == 1.0
    assert result.drifted is False
