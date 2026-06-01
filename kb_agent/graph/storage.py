from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from kb_agent.graph.features import Feature
from kb_agent.graph.hotpath import HotPathScore
from kb_agent.models.graph import SymbolEdge, SymbolNode


# ---------------------------------------------------------------------------
# Read-only interface
# ---------------------------------------------------------------------------

class ReadOnlyStorage(ABC):
    """Read-only interface for graph storage.

    Decouples consumers (e.g. the dashboard server) from the concrete
    ``GraphStorage`` implementation, making it easy to swap backends
    or inject test doubles.
    """

    @abstractmethod
    def load(self) -> tuple[list[SymbolNode], list[SymbolEdge]]:
        """Load nodes and edges from storage."""
        ...

    @abstractmethod
    def load_hotpath(self) -> dict[str, HotPathScore]:
        """Load hot-path scores from storage."""
        ...

    @abstractmethod
    def load_features(self) -> list[Feature]:
        """Load feature groups from storage."""
        ...


# ---------------------------------------------------------------------------
# Focused storage classes (SRP)
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path, model_class: type) -> list:
    """Load a JSONL file into a list of model instances."""
    items: list = []
    if not path.exists():
        return items
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(model_class(**json.loads(line)))
    return items


def _build_adjacency(
    nodes: list[SymbolNode],
    edges: list[SymbolEdge],
) -> dict[str, dict[str, list[str]]]:
    """Build {node_id: {"outgoing": [edge_idx], "incoming": [edge_idx]}}."""
    adj: dict[str, dict[str, list[str]]] = {}
    for node in nodes:
        adj[node.id] = {"outgoing": [], "incoming": []}
    for i, edge in enumerate(edges):
        edge_id = str(i)
        if edge.source in adj:
            adj[edge.source]["outgoing"].append(edge_id)
        if edge.target in adj:
            adj[edge.target]["incoming"].append(edge_id)
    return adj


class NodeEdgeStorage:
    """Handles nodes.jsonl, edges.jsonl, and adjacency.json."""

    def __init__(self, graph_dir: Path) -> None:
        self._dir = graph_dir

    def save(self, nodes: list[SymbolNode], edges: list[SymbolEdge]) -> None:
        """Write nodes.jsonl, edges.jsonl, adjacency.json."""
        self._dir.mkdir(parents=True, exist_ok=True)

        with open(self._dir / "nodes.jsonl", "w", encoding="utf-8") as f:
            for node in nodes:
                f.write(node.model_dump_json() + "\n")

        with open(self._dir / "edges.jsonl", "w", encoding="utf-8") as f:
            for edge in edges:
                f.write(edge.model_dump_json() + "\n")

        adj = _build_adjacency(nodes, edges)
        (self._dir / "adjacency.json").write_text(
            json.dumps(adj, indent=2), encoding="utf-8",
        )

    def load(self) -> tuple[list[SymbolNode], list[SymbolEdge]]:
        """Load graph from disk."""
        nodes = _load_jsonl(self._dir / "nodes.jsonl", SymbolNode)
        edges = _load_jsonl(self._dir / "edges.jsonl", SymbolEdge)
        return nodes, edges


class HotPathStorage:
    """Handles hotpath.json."""

    def __init__(self, graph_dir: Path) -> None:
        self._dir = graph_dir

    def save(self, scores: dict[str, HotPathScore]) -> None:
        """Write hotpath.json."""
        self._dir.mkdir(parents=True, exist_ok=True)
        data = {
            nid: {"node_id": s.node_id, "incoming_calls": s.incoming_calls, "hotness": s.hotness}
            for nid, s in scores.items()
        }
        (self._dir / "hotpath.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8",
        )

    def load(self) -> dict[str, HotPathScore]:
        """Load hot-path scores from disk."""
        path = self._dir / "hotpath.json"
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return {nid: HotPathScore(**s) for nid, s in data.items()}


class FeatureStorage:
    """Handles features.jsonl."""

    def __init__(self, graph_dir: Path) -> None:
        self._dir = graph_dir

    def save(self, features: list[Feature]) -> None:
        """Write features.jsonl."""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / "features.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for feat in features:
                data = {
                    "id": feat.id,
                    "name": feat.name,
                    "member_node_ids": feat.member_node_ids,
                    "naming_basis": feat.naming_basis,
                    "edge_density": feat.edge_density,
                }
                f.write(json.dumps(data) + "\n")

    def load(self) -> list[Feature]:
        """Load features from disk."""
        path = self._dir / "features.jsonl"
        if not path.exists():
            return []
        features: list[Feature] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                features.append(Feature(**json.loads(line)))
        return features


# ---------------------------------------------------------------------------
# Facade — backward-compatible public API
# ---------------------------------------------------------------------------

class GraphStorage(ReadOnlyStorage):
    """JSONL + adjacency index storage for the symbol graph.

    Delegates to focused storage classes internally while keeping the
    original public API intact.
    """

    def __init__(self, graph_dir: Path) -> None:
        self._node_edge = NodeEdgeStorage(graph_dir)
        self._hotpath = HotPathStorage(graph_dir)
        self._features = FeatureStorage(graph_dir)

    # -- Node / Edge delegates --

    def save(self, nodes: list[SymbolNode], edges: list[SymbolEdge]) -> None:
        """Write nodes.jsonl, edges.jsonl, adjacency.json."""
        self._node_edge.save(nodes, edges)

    def load(self) -> tuple[list[SymbolNode], list[SymbolEdge]]:
        """Load graph from disk."""
        return self._node_edge.load()

    # -- Hot-path delegates --

    def save_hotpath(self, scores: dict[str, HotPathScore]) -> None:
        """Write hotpath.json."""
        self._hotpath.save(scores)

    def load_hotpath(self) -> dict[str, HotPathScore]:
        """Load hot-path scores from disk."""
        return self._hotpath.load()

    # -- Feature delegates --

    def save_features(self, features: list[Feature]) -> None:
        """Write features.jsonl."""
        self._features.save(features)

    def load_features(self) -> list[Feature]:
        """Load features from disk."""
        return self._features.load()
