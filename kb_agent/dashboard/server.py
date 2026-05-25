"""FastAPI REST API backend for the interactive dashboard."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from kb_agent.graph.storage import GraphStorage
from kb_agent.views.base import ViewIDMapper

logger = logging.getLogger(__name__)


def create_app(kb_dir: Path) -> FastAPI:
    """Create FastAPI app serving dashboard UI and REST API."""
    app = FastAPI(title="KB Agent Dashboard", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:*", "http://127.0.0.1:*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    kb_dir = kb_dir.resolve()
    graph_dir = kb_dir / "graph"
    entries_dir = kb_dir / "entries"

    # Cache loaded data
    state: dict = {"mapper": None, "nodes": None, "edges": None}

    def get_mapper() -> ViewIDMapper:
        if state["mapper"] is None:
            storage = GraphStorage(graph_dir)
            state["nodes"], state["edges"] = storage.load()
            state["mapper"] = ViewIDMapper(state["nodes"], state["edges"])
        return state["mapper"]

    # --- REST API ---

    @app.get("/api/status")
    def api_status():
        manifest_path = kb_dir / "manifest.json"
        if not manifest_path.exists():
            return {"status": "not_initialized"}
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        mapper = get_mapper()
        manifest["graph"] = {
            "nodes": len(mapper.node_by_id),
            "edges": sum(len(v) for v in mapper.edges_by_source.values()),
        }
        return manifest

    @app.get("/api/nodes")
    def api_nodes(
        layer: str | None = Query(None),
        name: str | None = Query(None),
        file: str | None = Query(None),
    ):
        mapper = get_mapper()
        nodes = []
        for nid, node in mapper.node_by_id.items():
            if name and name.lower() not in node.name.lower():
                continue
            if file and file not in node.path:
                continue
            nodes.append({
                "id": nid,
                "name": node.name,
                "kind": node.kind.value,
                "path": node.path,
                "line_start": node.line_start,
                "line_end": node.line_end,
                "language": node.language.value,
                "signature": node.signature,
            })
        return {"nodes": nodes}

    @app.get("/api/edges")
    def api_edges(kind: str | None = Query(None)):
        mapper = get_mapper()
        edges = []
        for src, edge_list in mapper.edges_by_source.items():
            for e in edge_list:
                if kind and e.kind.value != kind:
                    continue
                edges.append({
                    "source": e.source,
                    "target": e.target,
                    "kind": e.kind.value,
                    "confidence": e.confidence,
                })
        return {"edges": edges}

    @app.get("/api/search")
    def api_search(q: str = Query(...), top_k: int = Query(10)):
        try:
            from kb_agent.query.engine import QueryEngine
            engine = QueryEngine(kb_dir)
            results = engine.query(q, top_k=top_k)
            entries_data = []
            for entry in results:
                entries_data.append({
                    "id": entry.id,
                    "layer": entry.layer.value,
                    "path": entry.static.path,
                    "line_start": entry.static.line_start,
                    "name": entry.static.signature or entry.id,
                    "summary": entry.ai.summary,
                    "kind": entry.static.kind.value,
                })
            return {"results": entries_data}
        except (FileNotFoundError, ImportError) as e:
            raise HTTPException(status_code=404, detail=str(e))

    @app.get("/api/node/{node_id:path}")
    def api_node_detail(node_id: str):
        mapper = get_mapper()

        # Try exact match
        node = mapper.node_by_id.get(node_id)
        if not node:
            # Try name match
            for nid, n in mapper.node_by_id.items():
                if n.name == node_id or nid == node_id:
                    node = n
                    node_id = nid
                    break

        if not node:
            raise HTTPException(status_code=404, detail="Node not found")

        # Connected edges
        outgoing = mapper.edges_by_source.get(node_id, [])
        incoming = mapper.edges_by_target.get(node_id, [])

        connections = []
        for e in outgoing:
            tgt = mapper.node_by_id.get(e.target)
            connections.append({
                "direction": "outgoing",
                "target_id": e.target,
                "target_name": tgt.name if tgt else e.target,
                "kind": e.kind.value,
                "confidence": e.confidence,
            })
        for e in incoming:
            src = mapper.node_by_id.get(e.source)
            connections.append({
                "direction": "incoming",
                "source_id": e.source,
                "source_name": src.name if src else e.source,
                "kind": e.kind.value,
                "confidence": e.confidence,
            })

        # Load KB entry
        entry_data = None
        from kb_agent.query.engine import entry_filename
        entry_path = entries_dir / entry_filename(node_id)
        if entry_path.exists():
            entry_data = json.loads(entry_path.read_text(encoding="utf-8"))

        # Hot-path score
        hotpath = GraphStorage(graph_dir).load_hotpath()
        hp = hotpath.get(node_id)

        return {
            "id": node_id,
            "name": node.name,
            "kind": node.kind.value,
            "path": node.path,
            "line_start": node.line_start,
            "line_end": node.line_end,
            "language": node.language.value,
            "signature": node.signature,
            "modifiers": node.modifiers,
            "docstring": node.docstring,
            "connections": connections,
            "entry": entry_data,
            "hotness": hp.hotness if hp else None,
            "incoming_calls": hp.incoming_calls if hp else None,
        }

    @app.get("/api/hotpath")
    def api_hotpath():
        scores = GraphStorage(graph_dir).load_hotpath()
        return {
            "scores": [
                {"node_id": nid, "hotness": s.hotness, "incoming_calls": s.incoming_calls}
                for nid, s in scores.items()
            ]
        }

    @app.get("/api/features")
    def api_features():
        features = GraphStorage(graph_dir).load_features()
        return {
            "features": [
                {
                    "id": f.id,
                    "name": f.name,
                    "members": f.member_node_ids,
                    "naming_basis": f.naming_basis,
                    "edge_density": f.edge_density,
                }
                for f in features
            ]
        }

    @app.get("/api/file/{file_path:path}")
    def api_file_source(file_path: str, start: int = Query(0), end: int = Query(0)):
        # Prevent path traversal — resolved must be contained within repo root
        repo_root = kb_dir.parent.resolve()
        resolved = (repo_root / file_path).resolve()
        try:
            if os.path.commonpath([str(resolved), str(repo_root)]) != str(repo_root):
                raise HTTPException(status_code=403, detail="Access denied")
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied")

        if not resolved.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        try:
            lines = resolved.read_text(encoding="utf-8").splitlines()
            if start > 0:
                lines = lines[start - 1:]
            if end > 0:
                lines = lines[:end - start + 1]
            return {"path": file_path, "lines": lines, "total": len(lines)}
        except OSError as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/versions")
    def api_versions():
        try:
            from kb_agent.graph.temporal import TemporalGraphManager
            manager = TemporalGraphManager(graph_dir)
            versions = manager.list_versions()
            return {"versions": [
                {
                    "version_id": v.version_id,
                    "node_count": v.node_count,
                    "edge_count": v.edge_count,
                    "commit_hash": v.commit_hash,
                    "parent_version": v.parent_version,
                }
                for v in versions
            ]}
        except Exception:
            return {"versions": []}

    @app.get("/api/stats")
    def api_stats():
        mapper = get_mapper()
        kind_counts: dict[str, int] = {}
        lang_counts: dict[str, int] = {}
        for node in state["nodes"]:
            kind_counts[node.kind.value] = kind_counts.get(node.kind.value, 0) + 1
            lang_counts[node.language.value] = lang_counts.get(node.language.value, 0) + 1
        return {
            "node_count": len(mapper.node_by_id),
            "edge_count": sum(len(v) for v in mapper.edges_by_source.values()),
            "by_kind": kind_counts,
            "by_language": lang_counts,
        }

    # --- Static files ---
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
