from datetime import datetime, timedelta

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
    assert result.score == 10.0
