from __future__ import annotations

import json
from pathlib import Path

from kb_agent.graph.features import Feature
from kb_agent.models.graph import SymbolEdge, SymbolNode


class GraphStorage:
    """JSONL + adjacency index storage for the symbol graph."""

    def __init__(self, graph_dir: Path) -> None:
        self._dir = graph_dir

    def save(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
    ) -> None:
        """Write nodes.jsonl, edges.jsonl, adjacency.json."""
        self._dir.mkdir(parents=True, exist_ok=True)

        nodes_path = self._dir / "nodes.jsonl"
        with open(nodes_path, "w", encoding="utf-8") as f:
            for node in nodes:
                f.write(node.model_dump_json() + "\n")

        edges_path = self._dir / "edges.jsonl"
        with open(edges_path, "w", encoding="utf-8") as f:
            for edge in edges:
                f.write(edge.model_dump_json() + "\n")

        adjacency = self._build_adjacency(nodes, edges)
        adj_path = self._dir / "adjacency.json"
        adj_path.write_text(
            json.dumps(adjacency, indent=2), encoding="utf-8",
        )

    def load(self) -> tuple[list[SymbolNode], list[SymbolEdge]]:
        """Load graph from disk."""
        nodes = self._load_jsonl(self._dir / "nodes.jsonl", SymbolNode)
        edges = self._load_jsonl(self._dir / "edges.jsonl", SymbolEdge)
        return nodes, edges

    def save_features(self, features: list[Feature]) -> None:
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

    def load_features(self) -> list[Feature]:
        """Load features from disk."""
        path = self._dir / "features.jsonl"
        if not path.exists():
            return []
        features: list[Feature] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                data = json.loads(line)
                features.append(Feature(**data))
        return features

    def _build_adjacency(
        self,
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

    @staticmethod
    def _load_jsonl(path: Path, model_class: type) -> list:
        items = []
        if not path.exists():
            return items
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append(model_class(**json.loads(line)))
        return items
