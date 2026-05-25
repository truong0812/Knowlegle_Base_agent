"""MCP tool implementations wrapping existing KB engines."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from kb_agent.graph.storage import GraphStorage
from kb_agent.models.graph import EdgeKind
from kb_agent.views.base import ViewIDMapper

logger = logging.getLogger(__name__)


class KBTools:
    """Stateful tool provider — loads graph once, serves all tools."""

    def __init__(self, kb_dir: Path) -> None:
        self._kb_dir = kb_dir.resolve()
        self._graph_dir = kb_dir / "graph"
        self._entries_dir = kb_dir / "entries"
        self._mapper: ViewIDMapper | None = None
        self._nodes = None
        self._edges = None

    def _ensure_loaded(self) -> ViewIDMapper:
        if self._mapper is None:
            storage = GraphStorage(self._graph_dir)
            self._nodes, self._edges = storage.load()
            self._mapper = ViewIDMapper(self._nodes, self._edges)
        return self._mapper

    def _load_entry(self, entry_id: str) -> dict | None:
        from kb_agent.query.engine import entry_filename
        filename = entry_filename(entry_id)
        path = self._entries_dir / filename
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _load_manifest(self) -> dict | None:
        path = self._kb_dir / "manifest.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    # --- Tool implementations ---

    def kb_status(self) -> str:
        """Return index health and statistics."""
        manifest = self._load_manifest()
        if not manifest:
            return "Knowledge base not initialized. Run `kb-agent analyze` first."

        mapper = self._ensure_loaded()
        node_count = len(mapper.node_by_id)
        edge_count = sum(len(v) for v in mapper.edges_by_source.values())
        edge_kinds: dict[str, int] = {}
        for edges in mapper.edges_by_source.values():
            for e in edges:
                edge_kinds[e.kind.value] = edge_kinds.get(e.kind.value, 0) + 1

        lines = [
            f"Source: {manifest.get('source_repo', 'unknown')}",
            f"Languages: {', '.join(manifest.get('languages', []))}",
            f"Total entries: {manifest.get('stats', {}).get('total_entries', 0)}",
            f"Graph: {node_count} nodes, {edge_count} edges",
            f"Edge types: {json.dumps(edge_kinds)}",
            f"Avg confidence: {manifest.get('stats', {}).get('avg_confidence', 0):.2f}",
            f"By layer: {json.dumps(manifest.get('stats', {}).get('by_layer', {}))}",
        ]
        return "\n".join(lines)

    def kb_search(self, query: str, top_k: int = 5) -> str:
        """Search symbols by name or meaning using FAISS semantic search."""
        try:
            from kb_agent.query.engine import QueryEngine
            engine = QueryEngine(self._kb_dir)
            results = engine.query(query, top_k=top_k)
        except (FileNotFoundError, ImportError) as e:
            return f"Search unavailable: {e}"

        if not results:
            return f"No results found for: '{query}'"

        lines = [f"Found {len(results)} results for: '{query}'\n"]
        for entry in results:
            lines.append(f"[{entry.layer.value}] {entry.id}")
            if entry.static.signature:
                lines.append(f"  Signature: {entry.static.signature}")
            if entry.ai.summary:
                lines.append(f"  Summary: {entry.ai.summary}")
            lines.append(f"  Location: {entry.static.path}:{entry.static.line_start}")
            lines.append("")
        return "\n".join(lines)

    def kb_context(self, question: str) -> str:
        """Build relevant context for a task using graph-aware retrieval."""
        try:
            from kb_agent.query.retrieval import RetrievalEngine
            engine = RetrievalEngine(self._kb_dir)
            result = engine.retrieve(question)
            return result.context
        except (FileNotFoundError, ImportError) as e:
            return f"Context unavailable: {e}"

    def kb_callers(self, symbol: str) -> str:
        """Find what calls a function/method."""
        mapper = self._ensure_loaded()
        node_id = self._resolve_node(symbol)
        if not node_id:
            return f"Symbol not found: {symbol}"

        callers = mapper.edges_by_target.get(node_id, [])
        call_edges = [e for e in callers if e.kind in (EdgeKind.CALLS, EdgeKind.IMPORTS)]

        if not call_edges:
            return f"No callers found for: {symbol}"

        lines = [f"Callers of {symbol} ({len(call_edges)}):\n"]
        for edge in call_edges:
            src = mapper.node_by_id.get(edge.source)
            src_name = src.name if src else edge.source
            conf = f" (conf: {edge.confidence:.2f})" if edge.confidence < 1.0 else ""
            lines.append(f"  {src_name} --{edge.kind.value}--> {symbol}{conf}")
        return "\n".join(lines)

    def kb_callees(self, symbol: str) -> str:
        """Find what a function/method calls."""
        mapper = self._ensure_loaded()
        node_id = self._resolve_node(symbol)
        if not node_id:
            return f"Symbol not found: {symbol}"

        callees = mapper.edges_by_source.get(node_id, [])
        call_edges = [e for e in callees if e.kind in (EdgeKind.CALLS, EdgeKind.IMPORTS)]

        if not call_edges:
            return f"No callees found for: {symbol}"

        lines = [f"Callees of {symbol} ({len(call_edges)}):\n"]
        for edge in call_edges:
            tgt = mapper.node_by_id.get(edge.target)
            tgt_name = tgt.name if tgt else edge.target
            conf = f" (conf: {edge.confidence:.2f})" if edge.confidence < 1.0 else ""
            lines.append(f"  {symbol} --{edge.kind.value}--> {tgt_name}{conf}")
        return "\n".join(lines)

    def kb_impact(self, symbol: str, depth: int = 2) -> str:
        """Analyze what code is affected by changing a symbol."""
        mapper = self._ensure_loaded()
        node_id = self._resolve_node(symbol)
        if not node_id:
            return f"Symbol not found: {symbol}"

        # BFS to find all nodes affected
        visited: set[str] = {node_id}
        affected: list[tuple[str, int, str]] = []
        queue = [(node_id, 0)]

        while queue:
            current_id, current_depth = queue.pop(0)
            if current_depth >= depth:
                continue

            # Find callers (incoming edges) — who depends on this
            for edge in mapper.edges_by_target.get(current_id, []):
                if edge.source not in visited and edge.kind in (
                    EdgeKind.CALLS, EdgeKind.IMPORTS, EdgeKind.USES_TYPE,
                    EdgeKind.INHERITS, EdgeKind.IMPLEMENTS,
                ):
                    visited.add(edge.source)
                    src = mapper.node_by_id.get(edge.source)
                    name = src.name if src else edge.source
                    affected.append((name, current_depth + 1, edge.kind.value))
                    queue.append((edge.source, current_depth + 1))

        if not affected:
            return f"No impact found for: {symbol} (depth={depth})"

        lines = [f"Impact of changing {symbol} ({len(affected)} affected symbols):\n"]
        for name, d, kind in sorted(affected, key=lambda x: x[1]):
            indent = "  " * (d + 1)
            lines.append(f"{indent}[depth={d}] {name} ({kind})")
        return "\n".join(lines)

    def kb_node(self, symbol: str) -> str:
        """Get details about a specific symbol."""
        mapper = self._ensure_loaded()
        node_id = self._resolve_node(symbol)
        if not node_id:
            return f"Symbol not found: {symbol}"

        node = mapper.node_by_id.get(node_id)
        if not node:
            return f"Node not found: {node_id}"

        lines = [
            f"Node: {node.name}",
            f"  ID: {node.id}",
            f"  Kind: {node.kind.value}",
            f"  Path: {node.path}:{node.line_start}-{node.line_end}",
            f"  Language: {node.language.value}",
        ]
        if node.signature:
            lines.append(f"  Signature: {node.signature}")
        if node.docstring:
            lines.append(f"  Docstring: {node.docstring}")
        if node.modifiers:
            lines.append(f"  Modifiers: {', '.join(node.modifiers)}")

        # Connected edges
        outgoing = mapper.edges_by_source.get(node_id, [])
        incoming = mapper.edges_by_target.get(node_id, [])
        lines.append(f"\n  Connections: {len(outgoing)} outgoing, {len(incoming)} incoming")

        # Load KB entry if available
        entry = self._load_entry(node_id)
        if entry:
            ai = entry.get("ai", {})
            if ai.get("summary"):
                lines.append(f"\n  AI Summary: {ai['summary']}")
            if ai.get("tags"):
                lines.append(f"  Tags: {', '.join(ai['tags'])}")

        return "\n".join(lines)

    def kb_explore(self, question: str, top_k: int = 5) -> str:
        """Return source code sections for symbols related to a question."""
        try:
            from kb_agent.query.retrieval import RetrievalEngine
            engine = RetrievalEngine(self._kb_dir)
            result = engine.retrieve(question, top_k=top_k)
        except (FileNotFoundError, ImportError) as e:
            return f"Explore unavailable: {e}"

        if not result.entries:
            return "No results found."

        lines = [result.context]

        # Attempt to read source for top entries
        for entry in result.entries[:3]:
            if not entry.static.path or not entry.static.signature:
                continue
            src_path = Path(entry.static.path)
            if not src_path.exists():
                # Try relative to kb_dir parent (the repo root)
                src_path = self._kb_dir.parent / entry.static.path
            if src_path.exists():
                try:
                    all_lines = src_path.read_text(encoding="utf-8").splitlines()
                    start = max(0, entry.static.line_start - 1)
                    end = min(len(all_lines), entry.static.line_end)
                    source_snippet = "\n".join(
                        f"  {i+1}: {line}" for i, line in enumerate(all_lines[start:end], start=start)
                    )
                    lines.append(f"\n--- Source: {entry.static.path} ---")
                    lines.append(source_snippet)
                except OSError:
                    pass

        return "\n".join(lines)

    def kb_files(self) -> str:
        """Get indexed file structure."""
        mapper = self._ensure_loaded()
        files: dict[str, list[str]] = {}
        for node in self._nodes:
            path = node.path
            files.setdefault(path, []).append(f"  {node.kind.value} {node.name}")

        if not files:
            return "No files indexed."

        lines = [f"Indexed files ({len(files)}):\n"]
        for path in sorted(files):
            lines.append(f"{path}:")
            lines.extend(files[path][:10])
            if len(files[path]) > 10:
                lines.append(f"  ... and {len(files[path]) - 10} more symbols")
        return "\n".join(lines)

    def _resolve_node(self, symbol: str) -> str | None:
        """Resolve a symbol name to a node ID (exact or fuzzy)."""
        mapper = self._ensure_loaded()

        # Exact match
        if symbol in mapper.node_by_id:
            return symbol

        # Name match
        for nid, node in mapper.node_by_id.items():
            if node.name == symbol:
                return nid

        # Partial match
        symbol_lower = symbol.lower()
        for nid, node in mapper.node_by_id.items():
            if symbol_lower in node.name.lower() or node.name.lower() in symbol_lower:
                return nid

        return None
