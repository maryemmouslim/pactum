from pactum.monitoring.drift.chi_squared import ChiSquaredDetector
from pactum.monitoring.drift.freshness import FreshnessDetector
from pactum.monitoring.drift.ks import KSDetector
from pactum.monitoring.drift.protocol import DriftDetector
from pactum.monitoring.drift.psi import PSIDetector

_detectors: dict[str, DriftDetector] = {}


def register_detector(name: str, detector: DriftDetector) -> None:
    """Register a drift detector under a name (e.g. "psi", "ks")."""
    _detectors[name] = detector


def get_detector(name: str) -> DriftDetector:
    """Return the drift detector registered under a given name."""
    try:
        return _detectors[name]
    except KeyError:
        raise KeyError(f"No drift detector registered as '{name}'") from None


register_detector("psi", PSIDetector())
register_detector("ks", KSDetector())
register_detector("chi_squared", ChiSquaredDetector())
register_detector("freshness_delta", FreshnessDetector())
