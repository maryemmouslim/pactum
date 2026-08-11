from dagster import DagsterInstance

from pactum.monitoring.pipeline_logs import ensure_dagster_home
from pactum.orchestration.definitions import DATASET_ID, defs
from pactum.sources.registry import load_persisted_registrations

if __name__ == "__main__":
    # restore persisted source registrations so adapters are available
    load_persisted_registrations()
    ensure_dagster_home()
    job_def = defs.resolve_job_def("monitoring_job")
    with DagsterInstance.get() as instance:
        result = job_def.execute_in_process(instance=instance, tags={"dataset_id": DATASET_ID})
    print("success=", result.success)
    for event in result.all_events:
        print(event)
