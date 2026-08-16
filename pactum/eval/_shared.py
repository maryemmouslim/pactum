import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import psycopg

from pactum.settings import settings


def import_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cleanup_eval_dataset(dataset_id: str) -> None:
    """Delete every row an eval scenario may have created for this dataset_id.

    Callers run this both before and after each scenario so a rerun always
    starts clean instead of accumulating rows across runs (e.g. tripping the
    single-active-contract-version constraint or an incident signature clash).
    """
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as conn:
        conn.execute(
            "DELETE FROM refinements WHERE incident_id IN "
            "(SELECT id FROM incidents WHERE dataset_id = %(id)s)",
            {"id": dataset_id},
        )
        conn.execute(
            "DELETE FROM explanations WHERE incident_id IN "
            "(SELECT id FROM incidents WHERE dataset_id = %(id)s)",
            {"id": dataset_id},
        )
        conn.execute("DELETE FROM incidents WHERE dataset_id = %(id)s", {"id": dataset_id})
        conn.execute("DELETE FROM contracts WHERE dataset_id = %(id)s", {"id": dataset_id})
