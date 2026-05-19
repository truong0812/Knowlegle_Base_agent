"""Cross-language bridge detection.

Detects inter-language connections between symbols:
- HTTP API bridges: C# controller routes matching Python HTTP client calls
- Data contract bridges: shared DTO class names between languages
- Message queue bridges: shared topic/channel string literals
"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

from kb_agent.models.graph import EdgeKind, Language, SymbolEdge, SymbolNode

logger = logging.getLogger(__name__)

# Bridge confidence ranges
BRIDGE_CONFIDENCE = {
    "http_exact_route": 0.70,
    "http_pattern_match": 0.50,
    "data_contract_name_fields": 0.60,
    "data_contract_name_only": 0.40,
    "message_queue": 0.35,
}


class LanguageBridge(ABC):
    """Abstract base for cross-language bridge detection."""

    @abstractmethod
    def detect_bridges(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
    ) -> list[SymbolEdge]:
        ...


class HttpApiBridge(LanguageBridge):
    """Detect C# HTTP endpoint methods matching Python HTTP client calls.

    C# side: methods with [HttpGet("/api/...")] etc. modifiers
    Python side: calls to requests.get("/api/...") etc.
    """

    # Regex to extract route templates from C# attributes
    _ROUTE_RE = re.compile(r"\[Http(?:Get|Post|Put|Delete|Patch)\s*\(\s*\"([^\"]+)\"", re.IGNORECASE)

    # Regex to extract URL patterns from Python call strings
    _URL_RE = re.compile(r"(?:get|post|put|delete|patch|request)\s*\(\s*[\"'](/[^\s\"']+)", re.IGNORECASE)

    def detect_bridges(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
    ) -> list[SymbolEdge]:
        csharp_endpoints = self._find_csharp_endpoints(nodes)
        python_clients = self._find_python_clients(nodes, edges)

        if not csharp_endpoints or not python_clients:
            return []

        bridges: list[SymbolEdge] = []
        for py_id, py_route in python_clients:
            for cs_id, cs_route in csharp_endpoints:
                conf, match_type = self._match_routes(cs_route, py_route)
                if conf > 0:
                    bridges.append(SymbolEdge(
                        source=py_id,
                        target=cs_id,
                        kind=EdgeKind.BRIDGES_TO,
                        confidence=conf,
                        source_type="heuristic",
                        resolution=f"bridge_http_{match_type}",
                        bridge_metadata={"protocol": "http", "route": cs_route},
                    ))
        return bridges

    def _find_csharp_endpoints(self, nodes: list[SymbolNode]) -> list[tuple[str, str]]:
        """Find C# methods with HTTP endpoint attributes."""
        results: list[tuple[str, str]] = []
        for node in nodes:
            if node.language != Language.CSHARP:
                continue
            for mod in node.modifiers:
                m = self._ROUTE_RE.search(mod)
                if m:
                    results.append((node.id, m.group(1)))
        return results

    def _find_python_clients(
        self, nodes: list[SymbolNode], edges: list[SymbolEdge],
    ) -> list[tuple[str, str]]:
        """Find Python nodes that make HTTP calls with URL strings.

        Heuristic: look at function/method names containing 'request', 'fetch',
        'call_api' or signatures containing URL-like strings.
        """
        results: list[tuple[str, str]] = []
        for node in nodes:
            if node.language != Language.PYTHON:
                continue
            # Check signature for URL patterns
            if node.signature:
                m = self._URL_RE.search(node.signature)
                if m:
                    results.append((node.id, m.group(1)))
                    continue
            # Check docstring for URL patterns
            if node.docstring:
                m = self._URL_RE.search(node.docstring)
                if m:
                    results.append((node.id, m.group(1)))
        return results

    @staticmethod
    def _match_routes(cs_route: str, py_route: str) -> tuple[float, str]:
        """Match a C# route template against a Python URL string."""
        # Normalize: strip trailing slashes
        cs = cs_route.rstrip("/")
        py = py_route.rstrip("/")

        if cs == py:
            return BRIDGE_CONFIDENCE["http_exact_route"], "exact"

        # Pattern match: C# route templates like /api/users/{id} match /api/users/123
        cs_pattern = re.sub(r"\{[^}]+\}", r"[^/]+", cs)
        if re.fullmatch(cs_pattern, py):
            return BRIDGE_CONFIDENCE["http_pattern_match"], "pattern"

        return 0.0, ""


class DataContractBridge(LanguageBridge):
    """Detect shared DTO/data class names between languages."""

    # Names that are too generic to bridge on
    _GENERIC_NAMES = frozenset({
        "config", "settings", "options", "result", "response", "request",
        "error", "exception", "status", "info", "data", "model", "dto",
    })

    def detect_bridges(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
    ) -> list[SymbolEdge]:
        # Group class nodes by language
        by_lang: dict[Language, dict[str, list[SymbolNode]]] = {}
        for node in nodes:
            if node.kind.value != "class":
                continue
            name_lower = node.name.lower()
            if name_lower in self._GENERIC_NAMES:
                continue
            by_lang.setdefault(node.language, {}).setdefault(name_lower, []).append(node)

        # Find matching class names across languages
        bridges: list[SymbolEdge] = []
        languages = list(by_lang.keys())
        for i, lang_a in enumerate(languages):
            for lang_b in languages[i + 1:]:
                for name, nodes_a in by_lang[lang_a].items():
                    nodes_b = by_lang.get(lang_b, {}).get(name)
                    if not nodes_b:
                        continue
                    # Bridge first match per name
                    na, nb = nodes_a[0], nodes_b[0]
                    # Check field similarity
                    fields_a = len(na.parameters)
                    fields_b = len(nb.parameters)
                    if fields_a > 0 and fields_b > 0 and abs(fields_a - fields_b) <= max(fields_a, fields_b) * 0.5:
                        conf = BRIDGE_CONFIDENCE["data_contract_name_fields"]
                        res = "bridge_data_contract_fields"
                    else:
                        conf = BRIDGE_CONFIDENCE["data_contract_name_only"]
                        res = "bridge_data_contract_name"

                    bridges.append(SymbolEdge(
                        source=na.id,
                        target=nb.id,
                        kind=EdgeKind.BRIDGES_TO,
                        confidence=conf,
                        source_type="heuristic",
                        resolution=res,
                        bridge_metadata={"protocol": "data_contract", "shared_name": name},
                    ))
        return bridges


class MessageQueueBridge(LanguageBridge):
    """Detect shared message queue topic/channel names between languages.

    Heuristic: look for string literals containing common queue patterns
    in function names (e.g., 'user-events', 'order_queue').
    """

    _TOPIC_RE = re.compile(r'[a-z][a-z0-9]*[-_][a-z0-9_-]+', re.IGNORECASE)

    def detect_bridges(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
    ) -> list[SymbolEdge]:
        # Extract potential topic names from node names/signatures
        topics_by_node: dict[str, list[str]] = {}
        for node in nodes:
            topics: list[str] = []
            # Check name for topic-like patterns
            for m in self._TOPIC_RE.finditer(node.name):
                topics.append(m.group(0).lower())
            # Check docstring
            if node.docstring:
                for m in self._TOPIC_RE.finditer(node.docstring):
                    topics.append(m.group(0).lower())
            if topics:
                topics_by_node[node.id] = list(set(topics))

        if len(topics_by_node) < 2:
            return []

        # Find nodes sharing topic names across languages
        nodes_by_lang: dict[str, str] = {}
        for node_dict_like in nodes:
            # Access node data
            pass

        # Group by shared topics
        topic_to_nodes: dict[str, list[tuple[str, Language]]] = {}
        for nid, topics in topics_by_node.items():
            # We need language info - access from node
            # Find node from the input list
            pass

        # Simplified: find nodes from different languages sharing topic names
        node_lang: dict[str, Language] = {n.id: n.language for n in nodes}

        bridges: list[SymbolEdge] = []
        seen_pairs: set[tuple[str, str]] = set()
        for nid_a, topics_a in topics_by_node.items():
            for nid_b, topics_b in topics_by_node.items():
                if nid_a == nid_b:
                    continue
                if node_lang.get(nid_a) == node_lang.get(nid_b):
                    continue
                shared = set(topics_a) & set(topics_b)
                if not shared:
                    continue
                pair = tuple(sorted([nid_a, nid_b]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                bridges.append(SymbolEdge(
                    source=nid_a,
                    target=nid_b,
                    kind=EdgeKind.BRIDGES_TO,
                    confidence=BRIDGE_CONFIDENCE["message_queue"],
                    source_type="heuristic",
                    resolution="bridge_message_queue",
                    bridge_metadata={"protocol": "message_queue", "shared_topics": ",".join(sorted(shared)[:3])},
                ))
        return bridges


class BridgeDetector:
    """Orchestrates all bridge detection strategies."""

    def __init__(self) -> None:
        self._strategies: list[LanguageBridge] = [
            HttpApiBridge(),
            DataContractBridge(),
            MessageQueueBridge(),
        ]

    def detect_bridges(
        self,
        nodes: list[SymbolNode],
        edges: list[SymbolEdge],
    ) -> list[SymbolEdge]:
        """Run all bridge strategies and deduplicate results."""
        all_bridges: list[SymbolEdge] = []
        seen_pairs: set[tuple[str, str]] = set()

        # Check that multiple languages are present
        languages = {n.language for n in nodes}
        if len(languages) < 2:
            return []

        for strategy in self._strategies:
            try:
                bridges = strategy.detect_bridges(nodes, edges)
                for bridge in bridges:
                    pair = tuple(sorted([bridge.source, bridge.target]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        all_bridges.append(bridge)
            except Exception:
                logger.debug("Bridge strategy %s failed", type(strategy).__name__, exc_info=True)

        if all_bridges:
            logger.info("Cross-language bridges detected: %d", len(all_bridges))
        return all_bridges
