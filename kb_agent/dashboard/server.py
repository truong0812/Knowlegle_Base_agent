"""FastAPI REST API backend for the interactive dashboard."""

import orjson
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from kb_agent.graph.storage import GraphStorage, ReadOnlyStorage
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

    # Single storage instance — typed against the read-only interface
    storage: ReadOnlyStorage = GraphStorage(graph_dir)

    # Cache loaded data
    state: dict = {"mapper": None, "nodes": None, "edges": None, "hotpath": None, "features": None, "name_index": None}

    def kb_missing_error(message: str = "Knowledge base not found. Run analyze first.") -> dict:
        return {"code": "missing_kb", "message": message}

    def get_mapper() -> ViewIDMapper:
        if state["mapper"] is None:
            state["nodes"], state["edges"] = storage.load()
            state["mapper"] = ViewIDMapper(state["nodes"], state["edges"])
            state["name_index"] = {
                n.name: nid for nid, n in state["mapper"].node_by_id.items()
            }
        return state["mapper"]

    def get_hotpath() -> dict:
        if state["hotpath"] is None:
            state["hotpath"] = storage.load_hotpath()
        return state["hotpath"]

    def get_features() -> list:
        if state["features"] is None:
            state["features"] = storage.load_features()
        return state["features"]

    def get_entry_count(manifest: dict) -> int:
        manifest_total = manifest.get("stats", {}).get("total_entries")
        if isinstance(manifest_total, int):
            return manifest_total
        if entries_dir.exists():
            return sum(1 for path in entries_dir.glob("*.json") if path.is_file())
        return 0

    def load_arch_summary() -> str | None:
        arch_path = entries_dir / "arch_root.json"
        if not arch_path.exists():
            return None
        try:
            entry = orjson.loads(arch_path.read_bytes())
        except orjson.JSONDecodeError:
            logger.warning("Invalid JSON in %s", arch_path)
            return None
        ai = entry.get("ai", {})
        return ai.get("summary") or ai.get("purpose")

    def top_modules(nodes: list, limit: int = 8) -> list[str]:
        counts: dict[str, int] = {}
        for node in nodes:
            path = Path(node.path)
            parts = path.parts
            if len(parts) >= 2:
                module = ".".join(parts[:2])
            elif parts:
                module = parts[0]
            else:
                module = node.path
            if module:
                counts[module] = counts.get(module, 0) + 1
        return [
            name for name, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
        ]

    def node_detail_for_feature(node_id: str, hotpath: dict) -> dict | None:
        mapper = get_mapper()
        node = mapper.node_by_id.get(node_id)
        if node is None:
            return None
        hp = hotpath.get(node_id)
        return {
            "node_id": node_id,
            "name": node.name,
            "kind": node.kind.value,
            "language": node.language.value,
            "path": node.path,
            "line_start": node.line_start,
            "line_end": node.line_end,
            "signature": node.signature,
            "hotness": hp.hotness if hp else None,
            "incoming_calls": hp.incoming_calls if hp else None,
        }

    # --- REST API ---

    @app.get("/api/status")
    def api_status():
        manifest_path = kb_dir / "manifest.json"
        if not manifest_path.exists():
            return {"status": "not_initialized"}
        try:
            manifest = orjson.loads(manifest_path.read_bytes())
        except FileNotFoundError:
            return {"status": "not_initialized"}
        except orjson.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"Invalid manifest.json: {exc}") from exc
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

    @app.get("/api/overview")
    def api_overview():
        manifest_path = kb_dir / "manifest.json"
        empty_payload = {
            "summary": None,
            "source_repo": None,
            "created_at": None,
            "stats": None,
            "languages": [],
            "top_modules": [],
            "top_features": [],
            "top_hot_symbols": [],
        }
        if not manifest_path.exists():
            return {**empty_payload, "error": kb_missing_error()}

        try:
            manifest = orjson.loads(manifest_path.read_bytes())
        except FileNotFoundError:
            return {**empty_payload, "error": kb_missing_error()}
        except orjson.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"Invalid manifest.json: {exc}") from exc

        mapper = get_mapper()
        nodes = state["nodes"] or []
        edges = state["edges"] or []

        hotpath = get_hotpath()
        features = get_features()
        node_by_id = mapper.node_by_id

        top_hot_symbols = []
        for node_id, score in sorted(
            hotpath.items(),
            key=lambda item: (-item[1].hotness, -item[1].incoming_calls, item[0]),
        )[:10]:
            node = node_by_id.get(node_id)
            top_hot_symbols.append({
                "node_id": node_id,
                "name": node.name if node else node_id,
                "path": node.path if node else None,
                "line_start": node.line_start if node else None,
                "line_end": node.line_end if node else None,
                "hotness": score.hotness,
                "incoming_calls": score.incoming_calls,
            })

        top_features = [
            {
                "id": feature.id,
                "name": feature.name,
                "member_count": len(feature.member_node_ids),
                "naming_basis": feature.naming_basis,
                "edge_density": feature.edge_density,
            }
            for feature in sorted(
                features,
                key=lambda item: (-item.edge_density, -len(item.member_node_ids), item.name),
            )[:10]
        ]

        return {
            "summary": load_arch_summary(),
            "source_repo": manifest.get("source_repo"),
            "created_at": manifest.get("created_at"),
            "stats": {
                "total_entries": get_entry_count(manifest),
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
            "languages": manifest.get("languages", []),
            "top_modules": top_modules(nodes),
            "top_features": top_features,
            "top_hot_symbols": top_hot_symbols,
            "error": None,
        }

    @app.get("/api/node/{node_id:path}")
    def api_node_detail(node_id: str):
        mapper = get_mapper()

        # Try exact match
        node = mapper.node_by_id.get(node_id)
        if not node:
            # Try name match via index
            nid = state["name_index"].get(node_id)
            if nid:
                node = mapper.node_by_id.get(nid)
                node_id = nid

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
            entry_data = orjson.loads(entry_path.read_bytes())

        # Hot-path score
        hotpath = get_hotpath()
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
        hotpath = get_hotpath()
        return {
            "scores": [
                {"node_id": nid, "hotness": s.hotness, "incoming_calls": s.incoming_calls}
                for nid, s in hotpath.items()
            ]
        }

    @app.get("/api/features")
    def api_features():
        features = get_features()
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

    @app.get("/api/features/{feature_id:path}")
    def api_feature_detail(feature_id: str):
        features = get_features()
        feature = next((f for f in features if f.id == feature_id), None)
        if feature is None:
            raise HTTPException(status_code=404, detail="Feature not found")

        hotpath = get_hotpath()
        members = [
            detail
            for node_id in feature.member_node_ids
            if (detail := node_detail_for_feature(node_id, hotpath)) is not None
        ]
        related_files = sorted({member["path"] for member in members if member.get("path")})

        return {
            "id": feature.id,
            "name": feature.name,
            "naming_basis": feature.naming_basis,
            "edge_density": feature.edge_density,
            "member_count": len(feature.member_node_ids),
            "members": members,
            "related_files": related_files,
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
