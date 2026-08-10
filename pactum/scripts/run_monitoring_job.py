from dagster import DagsterInstance

from pactum.orchestration.definitions import defs
from pactum.sources.registry import load_persisted_registrations

if __name__ == "__main__":
    # restore persisted source registrations so adapters are available
    load_persisted_registrations()
    instance = DagsterInstance.ephemeral()
    job_def = defs.resolve_job_def("monitoring_job")
    result = job_def.execute_in_process(instance=instance)
    print("success=", result.success)
    for event in result.all_events:
        print(event)
