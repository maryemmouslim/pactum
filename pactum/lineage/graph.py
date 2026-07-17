import networkx as nx
import psycopg

from pactum.models import LineageEdge
from pactum.settings import settings


class LineageGraph:
    def __init__(self) -> None:
        self._graph: nx.DiGraph[str] = nx.DiGraph()

    def add_edge(self, upstream_dataset_id: str, downstream_dataset_id: str) -> None:
        self._graph.add_edge(upstream_dataset_id, downstream_dataset_id)

    def upstream_of(self, dataset_id: str) -> list[str]:
        if dataset_id not in self._graph:
            return []
        return list(self._graph.predecessors(dataset_id))

    def downstream_of(self, dataset_id: str) -> list[str]:
        if dataset_id not in self._graph:
            return []
        return list(self._graph.successors(dataset_id))


def _connect() -> psycopg.Connection:
    url = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


def save_edge(edge: LineageEdge) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO lineage_edges (upstream_dataset_id, downstream_dataset_id)
            VALUES (%(upstream_dataset_id)s, %(downstream_dataset_id)s)
            ON CONFLICT (upstream_dataset_id, downstream_dataset_id) DO NOTHING
            """,
            edge.model_dump(),
        )


def load_graph() -> LineageGraph:
    graph = LineageGraph()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT upstream_dataset_id, downstream_dataset_id FROM lineage_edges"
        ).fetchall()
    for upstream, downstream in rows:
        graph.add_edge(upstream, downstream)
    return graph
