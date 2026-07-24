import pytest

from pactum.monitoring.drift.chi_squared import ChiSquaredDetector
from pactum.monitoring.drift.freshness import FreshnessDetector
from pactum.monitoring.drift.ks import KSDetector
from pactum.monitoring.drift.psi import PSIDetector
from pactum.monitoring.drift.registry import get_detector


def test_built_in_detectors_are_pre_registered() -> None:
    assert isinstance(get_detector("psi"), PSIDetector)
    assert isinstance(get_detector("ks"), KSDetector)
    assert isinstance(get_detector("chi_squared"), ChiSquaredDetector)
    assert isinstance(get_detector("freshness_delta"), FreshnessDetector)


def test_get_detector_unknown_name_raises() -> None:
    with pytest.raises(KeyError):
        get_detector("nonexistent")
