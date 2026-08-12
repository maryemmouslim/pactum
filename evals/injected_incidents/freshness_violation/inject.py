from datetime import UTC, datetime, timedelta
from pathlib import Path

from pactum.eval.fixtures import write_csv


def inject(context: dict[str, object]) -> None:
    path = Path(str(context["data_dir"])) / f"{context['dataset_id']}.csv"
    stale = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    rows: list[dict[str, object]] = [
        {"order_id": "o1", "created_at": stale},
        {"order_id": "o2", "created_at": stale},
    ]
    write_csv(path, rows)
