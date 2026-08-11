import os
from datetime import datetime, timedelta
from pathlib import Path

from dagster import DagsterInstance, RunsFilter

from pactum.settings import settings


def ensure_dagster_home() -> str:
    """Make sure DAGSTER_HOME points at a real, persistent local directory.

    DagsterInstance.get() (used by run_monitoring_job.py and by this module)
    requires DAGSTER_HOME to already be set -- this is the one place that
    responsibility lives, so run history survives across processes instead
    of vanishing with DagsterInstance.ephemeral().
    """
    home = str(Path(settings.dagster_home).resolve())
    Path(home).mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("DAGSTER_HOME", home)
    return home


def fetch_recent_runs(
    dataset_id: str, around: datetime, window: timedelta = timedelta(days=3)
) -> dict[str, object]:
    """Return recent monitoring_job run records tagged with this dataset_id.

    Only runs that actually went through Dagster (the scheduled monitoring_job)
    show up here -- ad-hoc "Run checks" clicks in the UI call evaluate_contract
    directly and never create a Dagster run, so they're intentionally absent.

    Falls back to status="not_configured" if no persistent instance has ever
    been created yet (e.g. run_monitoring_job.py hasn't run locally), rather
    than crashing.
    """
    try:
        ensure_dagster_home()
        with DagsterInstance.get() as instance:
            records = instance.get_run_records(
                filters=RunsFilter(
                    tags={"dataset_id": dataset_id},
                    created_after=around - window,
                    created_before=around + window,
                )
            )
    except Exception:  # noqa: BLE001
        return {"status": "not_configured", "logs": []}

    return {
        "status": "ok",
        "logs": [
            {
                "run_id": record.dagster_run.run_id,
                "status": record.dagster_run.status.value,
                "start_time": record.start_time,
                "end_time": record.end_time,
            }
            for record in records
        ],
    }
