import sys
from datetime import datetime

from pactum.monitoring.calendar_store import add_event

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print(
            "Usage: python pactum/scripts/add_calendar_event.py "
            "<dataset_id|global> <deployment|holiday|regulatory|other> "
            "<description> <event_at ISO timestamp>"
        )
        sys.exit(1)

    dataset_arg, event_type, description, event_at_raw = sys.argv[1:]
    dataset_id = None if dataset_arg == "global" else dataset_arg

    event = add_event(
        event_type=event_type,  # type: ignore[arg-type]
        description=description,
        event_at=datetime.fromisoformat(event_at_raw),
        dataset_id=dataset_id,
    )
    print(f"ADDED {event.id} {event.event_type} {event.dataset_id or 'global'} {event.event_at}")
