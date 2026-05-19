"""Tests for cross-language bridge detection."""
from __future__ import annotations

import pytest

from kb_agent.graph.bridge import (
    BRIDGE_CONFIDENCE,
    BridgeDetector,
    DataContractBridge,
    HttpApiBridge,
    MessageQueueBridge,
)
from kb_agent.models.entry import Language, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.query.expander import ExpandedSubgraph, expand_from_seeds
from kb_agent.views.base import ViewIDMapper


def _node(
    name: str,
    lang: Language = Language.PYTHON,
    kind: SymbolKind = SymbolKind.FUNCTION,
    path: str = "svc.py",
    line: int = 1,
    mods: list[str] | None = None,
    sig: str | None = None,
    doc: str | None = None,
    params: list | None = None,
) -> SymbolNode:
    return SymbolNode(
        id=f"repo/{path}::{name}",
        name=name,
        kind=kind,
        language=lang,
        path=path,
        line_start=line,
        line_end=line + 5,
        modifiers=mods or [],
        signature=sig,
        docstring=doc,
        parameters=params or [],
    )


class TestHttpApiBridge:
    def test_detects_matching_routes(self):
        cs_node = _node(
            "GetUsers", Language.CSHARP, SymbolKind.METHOD,
            path="Controllers/UserController.cs", line=10,
            mods=['[HttpGet("/api/users")]'],
        )
        py_node = _node(
            "fetch_users", Language.PYTHON,
            path="client/api_client.py", line=5,
            sig='requests.get("/api/users")',
        )
        bridge = HttpApiBridge()
        edges = bridge.detect_bridges([cs_node, py_node], [])
        assert len(edges) == 1
        assert edges[0].kind == EdgeKind.BRIDGES_TO
        assert edges[0].confidence == BRIDGE_CONFIDENCE["http_exact_route"]
        assert edges[0].bridge_metadata["protocol"] == "http"

    def test_no_false_positive(self):
        cs_node = _node(
            "GetUsers", Language.CSHARP,
            mods=['[HttpGet("/api/users")]'],
        )
        py_node = _node(
            "do_something", Language.PYTHON,
            sig='requests.get("/api/orders")',
        )
        bridge = HttpApiBridge()
        edges = bridge.detect_bridges([cs_node, py_node], [])
        assert len(edges) == 0

    def test_confidence_exact(self):
        cs_node = _node("A", Language.CSHARP, mods=['[HttpGet("/api/test")]'])
        py_node = _node("B", Language.PYTHON, sig='requests.get("/api/test")')
        bridge = HttpApiBridge()
        edges = bridge.detect_bridges([cs_node, py_node], [])
        assert edges[0].confidence >= 0.65

    def test_confidence_pattern(self):
        cs_node = _node("A", Language.CSHARP, mods=['[HttpGet("/api/users/{id}")]'])
        py_node = _node("B", Language.PYTHON, sig='requests.get("/api/users/123")')
        bridge = HttpApiBridge()
        edges = bridge.detect_bridges([cs_node, py_node], [])
        assert len(edges) == 1
        assert edges[0].confidence == BRIDGE_CONFIDENCE["http_pattern_match"]


class TestDataContractBridge:
    def test_name_match_with_fields(self):
        cs_node = _node(
            "UserDto", Language.CSHARP, SymbolKind.CLASS,
            path="Models/UserDto.cs",
            params=[__import__("kb_agent.models.entry", fromlist=["Parameter"]).Parameter(name="id", type="int"),
                    __import__("kb_agent.models.entry", fromlist=["Parameter"]).Parameter(name="name", type="str")],
        )
        py_node = _node(
            "UserDto", Language.PYTHON, SymbolKind.CLASS,
            path="models/user_dto.py",
            params=[__import__("kb_agent.models.entry", fromlist=["Parameter"]).Parameter(name="id", type="int"),
                    __import__("kb_agent.models.entry", fromlist=["Parameter"]).Parameter(name="name", type="str")],
        )
        bridge = DataContractBridge()
        edges = bridge.detect_bridges([cs_node, py_node], [])
        assert len(edges) == 1
        assert edges[0].kind == EdgeKind.BRIDGES_TO

    def test_name_only_no_fields(self):
        cs_node = _node("Order", Language.CSHARP, SymbolKind.CLASS, path="Models/Order.cs")
        py_node = _node("Order", Language.PYTHON, SymbolKind.CLASS, path="models/order.py")
        bridge = DataContractBridge()
        edges = bridge.detect_bridges([cs_node, py_node], [])
        assert len(edges) == 1
        assert edges[0].confidence == BRIDGE_CONFIDENCE["data_contract_name_only"]

    def test_no_match(self):
        cs_node = _node("UserService", Language.CSHARP, SymbolKind.CLASS, path="Svc.cs")
        py_node = _node("OrderService", Language.PYTHON, SymbolKind.CLASS, path="svc.py")
        bridge = DataContractBridge()
        edges = bridge.detect_bridges([cs_node, py_node], [])
        assert len(edges) == 0


class TestMessageQueueBridge:
    def test_shared_topic(self):
        cs_node = _node(
            "handler", Language.CSHARP,
            path="Handlers/Events.cs",
            doc="listens to user-events queue",
        )
        py_node = _node(
            "processor", Language.PYTHON,
            path="workers/events.py",
            doc="publishes to user-events queue",
        )
        bridge = MessageQueueBridge()
        edges = bridge.detect_bridges([cs_node, py_node], [])
        assert len(edges) >= 1
        assert edges[0].kind == EdgeKind.BRIDGES_TO

    def test_no_match(self):
        cs_node = _node("order-handler", Language.CSHARP, path="h.cs")
        py_node = _node("user-processor", Language.PYTHON, path="w.py")
        bridge = MessageQueueBridge()
        edges = bridge.detect_bridges([cs_node, py_node], [])
        assert len(edges) == 0


class TestBridgeDetector:
    def test_dedup_same_pair(self):
        cs_node = _node("UserDto", Language.CSHARP, SymbolKind.CLASS, path="M.cs",
                        params=[__import__("kb_agent.models.entry", fromlist=["Parameter"]).Parameter(name="id", type="int")])
        py_node = _node("UserDto", Language.PYTHON, SymbolKind.CLASS, path="m.py",
                        params=[__import__("kb_agent.models.entry", fromlist=["Parameter"]).Parameter(name="id", type="int")])
        detector = BridgeDetector()
        edges = detector.detect_bridges([cs_node, py_node], [])
        # Should not duplicate the same bridge pair
        pairs = [(e.source, e.target) for e in edges]
        assert len(pairs) == len(set(pairs))

    def test_combines_multiple_strategies(self):
        cs_node = _node("UserDto", Language.CSHARP, SymbolKind.CLASS, path="M.cs",
                        params=[__import__("kb_agent.models.entry", fromlist=["Parameter"]).Parameter(name="id", type="int")])
        py_node = _node("UserDto", Language.PYTHON, SymbolKind.CLASS, path="m.py",
                        params=[__import__("kb_agent.models.entry", fromlist=["Parameter"]).Parameter(name="id", type="int")])
        detector = BridgeDetector()
        edges = detector.detect_bridges([cs_node, py_node], [])
        assert len(edges) >= 1

    def test_no_bridge_single_language(self):
        a = _node("A", Language.PYTHON)
        b = _node("B", Language.PYTHON)
        detector = BridgeDetector()
        edges = detector.detect_bridges([a, b], [])
        assert len(edges) == 0

    def test_bridge_metadata_stored(self):
        cs_node = _node("A", Language.CSHARP, mods=['[HttpGet("/api/test")]'])
        py_node = _node("B", Language.PYTHON, sig='requests.get("/api/test")')
        detector = BridgeDetector()
        edges = detector.detect_bridges([cs_node, py_node], [])
        assert len(edges) >= 1
        assert edges[0].bridge_metadata is not None
        assert edges[0].bridge_metadata.get("protocol") == "http"


class TestBridgeInExpansion:
    def test_bridge_edge_in_expansion(self):
        """Expander follows BRIDGES_TO edges."""
        a = _node("py_func", Language.PYTHON, path="client.py")
        b = _node("cs_handler", Language.CSHARP, path="Handler.cs")
        bridge_edge = SymbolEdge(
            source=a.id, target=b.id,
            kind=EdgeKind.BRIDGES_TO, confidence=0.70,
            source_type="heuristic", resolution="bridge_http_exact_route",
        )
        mapper = ViewIDMapper([a, b], [bridge_edge])
        subgraph = expand_from_seeds([a], mapper, max_hops=1, min_confidence=0.30)
        assert any(n.id == b.id for n in subgraph.all_nodes)

    def test_bridge_edge_in_context(self):
        """Composer renders bridge edges with protocol info."""
        from kb_agent.query.composer import _format_edges

        edge = SymbolEdge(
            source="repo/py.py::fetch", target="repo/cs.cs::handle",
            kind=EdgeKind.BRIDGES_TO, confidence=0.70,
            bridge_metadata={"protocol": "http", "route": "/api/users"},
        )
        text = _format_edges([edge])
        assert "bridges_to" in text
        assert "http" in text
