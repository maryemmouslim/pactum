import uuid

import psycopg
import pytest

from pactum.lineage.graph import load_graph, save_edge
from pactum.models import LineageEdge
from pactum.settings import settings


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


@pytest.fixture
def upstream_id() -> str:
    return f"test_upstream_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def downstream_id() -> str:
    return f"test_downstream_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _cleanup(upstream_id: str, downstream_id: str):  # type: ignore[no-untyped-def]
    yield
    with _connect() as conn:
        conn.execute(
            "DELETE FROM lineage_edges "
            "WHERE upstream_dataset_id = %(u)s AND downstream_dataset_id = %(d)s",
            {"u": upstream_id, "d": downstream_id},
        )


def test_save_edge_and_load_graph_round_trip(upstream_id: str, downstream_id: str) -> None:
    save_edge(LineageEdge(upstream_dataset_id=upstream_id, downstream_dataset_id=downstream_id))

    graph = load_graph()

    assert downstream_id in graph.downstream_of(upstream_id)
    assert upstream_id in graph.upstream_of(downstream_id)


def test_save_edge_is_idempotent_on_conflict(upstream_id: str, downstream_id: str) -> None:
    edge = LineageEdge(upstream_dataset_id=upstream_id, downstream_dataset_id=downstream_id)

    save_edge(edge)
    save_edge(edge)  # should not raise -- ON CONFLICT DO NOTHING

    graph = load_graph()
    assert graph.downstream_of(upstream_id) == [downstream_id]
