from pactum.monitoring.drift.psi import PSIDetector


def test_psi_detects_no_drift_for_identical_distributions() -> None:
    detector = PSIDetector()
    reference = list(range(1, 1001))
    current = list(range(1, 1001))

    result = detector.detect(reference, current)

    assert result.method == "psi"
    assert result.score == 0.0
    assert result.drifted is False


def test_psi_detects_drift_for_shifted_distribution() -> None:
    detector = PSIDetector()
    reference = list(range(1, 1001))
    current = [v + 500 for v in range(1, 1001)]

    result = detector.detect(reference, current)

    assert result.drifted is True
    assert result.score > 0.25


def test_psi_returns_insufficient_data_for_empty_reference() -> None:
    result = PSIDetector().detect([], [1, 2, 3])

    assert result.insufficient_data is True
    assert result.drifted is False


def test_psi_returns_insufficient_data_for_single_value_window() -> None:
    result = PSIDetector().detect([1], [1, 2, 3])

    assert result.insufficient_data is True
    assert result.drifted is False
