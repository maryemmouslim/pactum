from pactum.monitoring.drift.ks import KSDetector


def test_ks_detects_no_drift_for_identical_distributions() -> None:
    detector = KSDetector()
    reference = list(range(1, 1001))
    current = list(range(1, 1001))

    result = detector.detect(reference, current)

    assert result.method == "ks"
    assert result.score == 0.0
    assert result.drifted is False


def test_ks_detects_drift_for_shifted_distribution() -> None:
    detector = KSDetector()
    reference = list(range(1, 1001))
    current = [v + 500 for v in range(1, 1001)]

    result = detector.detect(reference, current)

    assert result.drifted is True
    assert result.details["p_value"] < 0.05


def test_ks_returns_insufficient_data_for_empty_reference() -> None:
    result = KSDetector().detect([], [1, 2, 3])

    assert result.insufficient_data is True
    assert result.drifted is False
