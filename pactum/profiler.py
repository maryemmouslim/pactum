import pandas as pd
import whylogs as why


def profile_columns(rows: list[tuple], columns: list[str]) -> dict[str, dict]:
    """Compute per-column statistics (nulls %, distinct count, min/max) for a sample of rows."""
    df = pd.DataFrame(rows, columns=columns)
    view = why.log(df).view()

    summary = {}
    for column in columns:
        col_view = view.get_column(column)
        counts = _summary_dict(col_view, "counts")
        distribution = _summary_dict(col_view, "distribution")
        cardinality = _summary_dict(col_view, "cardinality")

        n = counts.get("n", 0)
        null_count = counts.get("null", 0)
        summary[column] = {
            "null_percent": (null_count / n) if n else 0.0,
            "distinct_count": cardinality.get("est"),
            "min": distribution.get("min"),
            "max": distribution.get("max"),
        }
    return summary


def _summary_dict(col_view, metric_name: str) -> dict:
    metric = col_view.get_metric(metric_name)
    return metric.to_summary_dict() if metric else {}
