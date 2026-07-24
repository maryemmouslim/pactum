from pactum.monitoring.drift.chi_squared import ChiSquaredDetector


def test_chi_squared_detects_no_drift_for_identical_category_mix() -> None:
    detector = ChiSquaredDetector()
    reference = ["pending"] * 300 + ["shipped"] * 600 + ["cancelled"] * 100
    current = ["pending"] * 300 + ["shipped"] * 600 + ["cancelled"] * 100

    result = detector.detect(reference, current)

    assert result.method == "chi_squared"
    assert result.score == 0.0
    assert result.drifted is False


def test_chi_squared_detects_drift_for_shifted_category_mix() -> None:
    detector = ChiSquaredDetector()
    reference = ["pending"] * 300 + ["shipped"] * 600 + ["cancelled"] * 100
    current = ["pending"] * 300 + ["shipped"] * 200 + ["cancelled"] * 500

    result = detector.detect(reference, current)

    assert result.drifted is True
    assert result.details["p_value"] < 0.05


def test_chi_squared_returns_insufficient_data_for_empty_reference() -> None:
    result = ChiSquaredDetector().detect([], ["pending", "shipped"])

    assert result.insufficient_data is True
    assert result.drifted is False
