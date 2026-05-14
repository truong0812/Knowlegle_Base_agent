from __future__ import annotations

import asyncio

import pytest

from kb_agent.models.entry import Language, Layer, Parameter, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.views.base import ViewIDMapper

run = asyncio.run


def _make_node(
    name: str = "func",
    kind: SymbolKind = SymbolKind.FUNCTION,
    path: str = "src/main.py",
    line_start: int = 1,
    line_end: int = 10,
    language: Language = Language.PYTHON,
    signature: str | None = None,
) -> SymbolNode:
    return SymbolNode(
        id=f"repo/{path}::{name}",
        name=name,
        kind=kind,
        language=language,
        path=path,
        line_start=line_start,
        line_end=line_end,
        signature=signature or f"def {name}()",
    )


def _make_edge(
    source: str, target: str,
    kind: EdgeKind = EdgeKind.CALLS,
    confidence: float = 0.8,
) -> SymbolEdge:
    return SymbolEdge(
        source=source, target=target, kind=kind,
        confidence=confidence, source_type="heuristic", resolution="same_file",
    )


# ── ViewIDMapper Tests ─────────────────────────────────────────


class TestViewIDMapper:
    def test_group_by_depth_1(self):
        nodes = [
            _make_node("a", path="src/services/auth.py"),
            _make_node("b", path="src/models/user.py"),
            _make_node("c", path="tests/test_main.py"),
        ]
        mapper = ViewIDMapper(nodes, [])
        groups = mapper.group_nodes_by_depth(1)

        assert "src" in groups
        assert "tests" in groups
        assert len(groups["src"]) == 2
        assert len(groups["tests"]) == 1

    def test_group_by_depth_2(self):
        nodes = [
            _make_node("a", path="src/services/auth.py"),
            _make_node("b", path="src/models/user.py"),
            _make_node("c", path="src/services/token.py"),
        ]
        mapper = ViewIDMapper(nodes, [])
        groups = mapper.group_nodes_by_depth(2)

        assert "src/services" in groups
        assert "src/models" in groups
        assert len(groups["src/services"]) == 2
        assert len(groups["src/models"]) == 1

    def test_utility_detection(self):
        assert ViewIDMapper.is_utility_name("logger") is True
        assert ViewIDMapper.is_utility_name("config") is True
        assert ViewIDMapper.is_utility_name("auth_service") is False
        assert ViewIDMapper.is_utility_name("utils") is True
        assert ViewIDMapper.is_utility_name("main") is False
        assert ViewIDMapper.is_utility_name("serialize_data") is True

    def test_sanitize_path(self):
        assert ViewIDMapper.sanitize_path("src/services/auth.py") == "src_services_auth_py"
        assert ViewIDMapper.sanitize_path("main.py") == "main_py"

    def test_nodes_by_path(self):
        nodes = [
            _make_node("a", path="src/auth.py"),
            _make_node("b", path="src/auth.py"),
            _make_node("c", path="src/user.py"),
        ]
        mapper = ViewIDMapper(nodes, [])

        assert len(mapper.nodes_by_path["src/auth.py"]) == 2
        assert len(mapper.nodes_by_path["src/user.py"]) == 1

    def test_edges_by_source(self):
        n1 = _make_node("a", path="src/a.py")
        n2 = _make_node("b", path="src/b.py")
        edge = _make_edge(n1.id, n2.id)
        mapper = ViewIDMapper([n1, n2], [edge])

        assert n1.id in mapper.edges_by_source
        assert len(mapper.edges_by_source[n1.id]) == 1

    def test_find_module_for_file(self):
        mapper = ViewIDMapper([], [])
        assert mapper.find_module_for_file("src/services/auth.py", 1) == "src"
        assert mapper.find_module_for_file("src/services/auth.py", 2) == "src/services"


# ── ArchViewBuilder Tests ───────────────────────────────────────


class TestArchView:
    def test_single_entry(self):
        from kb_agent.views.arch_view import ArchViewBuilder

        nodes = [
            _make_node("main", path="src/main.py"),
            _make_node("User", kind=SymbolKind.CLASS, path="src/models/user.py"),
        ]
        edges = [_make_edge(nodes[0].id, nodes[1].id)]
        mapper = ViewIDMapper(nodes, edges)
        builder = ArchViewBuilder(mapper, llm=None)
        result = run(builder.build(nodes=nodes, edges=edges))

        assert len(result) == 1
        assert result[0].id == "arch.root"
        assert result[0].layer == Layer.ARCH

    def test_language_counts(self):
        from kb_agent.views.arch_view import ArchViewBuilder

        nodes = [
            _make_node("a", path="a.py", language=Language.PYTHON),
            _make_node("b", path="b.cs", language=Language.CSHARP),
            _make_node("c", path="c.py", language=Language.PYTHON),
        ]
        mapper = ViewIDMapper(nodes, [])
        builder = ArchViewBuilder(mapper, llm=None)
        result = run(builder.build(nodes=nodes, edges=[]))

        assert result[0].static.language == Language.CSHARP  # sorted first
        assert Language.PYTHON in result[0].static.languages
        assert Language.CSHARP in result[0].static.languages

    def test_entry_point_detection(self):
        from kb_agent.views.arch_view import ArchViewBuilder

        nodes = [
            _make_node("main", path="src/main.py"),
            _make_node("App", kind=SymbolKind.CLASS, path="src/__init__.py"),
            _make_node("helper", path="src/utils.py"),
        ]
        mapper = ViewIDMapper(nodes, [])
        builder = ArchViewBuilder(mapper, llm=None)
        result = run(builder.build(nodes=nodes, edges=[]))

        exports = result[0].static.exports
        assert any("main" in e for e in exports)
        assert any("App" in e for e in exports)
        assert not any("helper" in e for e in exports)


# ── ModViewBuilder Tests ────────────────────────────────────────


class TestModView:
    def test_grouping_by_depth(self):
        from kb_agent.views.mod_view import ModViewBuilder

        nodes = [
            _make_node("a", path="src/auth.py"),
            _make_node("b", path="src/user.py"),
            _make_node("c", path="tests/test.py"),
        ]
        mapper = ViewIDMapper(nodes, [])
        builder = ModViewBuilder(mapper, llm=None, depth=1)
        result = run(builder.build(nodes=nodes, edges=[]))

        mod_ids = {e.id for e in result}
        assert "mod.src" in mod_ids
        assert "mod.tests" in mod_ids

    def test_parent_refs(self):
        from kb_agent.views.mod_view import ModViewBuilder

        nodes = [_make_node("a", path="src/main.py")]
        mapper = ViewIDMapper(nodes, [])
        builder = ModViewBuilder(mapper, llm=None)
        result = run(builder.build(nodes=nodes, edges=[]))

        for entry in result:
            assert entry.parent == "arch.root"
            assert entry.layer == Layer.MOD

    def test_exports(self):
        from kb_agent.views.mod_view import ModViewBuilder

        nodes = [
            _make_node("User", kind=SymbolKind.CLASS, path="src/models.py"),
            _make_node("validate", kind=SymbolKind.FUNCTION, path="src/models.py"),
        ]
        mapper = ViewIDMapper(nodes, [])
        builder = ModViewBuilder(mapper, llm=None)
        result = run(builder.build(nodes=nodes, edges=[]))

        exports = result[0].static.exports
        assert "User" in exports
        assert "validate" in exports


# ── FileViewBuilder Tests ───────────────────────────────────────


class TestFileView:
    def test_one_per_file(self):
        from kb_agent.views.file_view import FileViewBuilder

        nodes = [
            _make_node("a", path="src/auth.py"),
            _make_node("b", path="src/auth.py"),
            _make_node("c", path="src/user.py"),
        ]
        mapper = ViewIDMapper(nodes, [])
        builder = FileViewBuilder(mapper, llm=None)
        result = run(builder.build(edges=[]))

        assert len(result) == 2
        file_ids = {e.id for e in result}
        assert "file.src_auth_py" in file_ids
        assert "file.src_user_py" in file_ids

    def test_intra_file_edges(self):
        from kb_agent.views.file_view import FileViewBuilder

        n1 = _make_node("a", path="src/auth.py")
        n2 = _make_node("b", path="src/auth.py")
        n3 = _make_node("c", path="src/user.py")

        intra = _make_edge(n1.id, n2.id, EdgeKind.CALLS)
        cross = _make_edge(n1.id, n3.id, EdgeKind.IMPORTS)

        mapper = ViewIDMapper([n1, n2, n3], [intra, cross])
        builder = FileViewBuilder(mapper, llm=None)
        result = run(builder.build(edges=[intra, cross]))

        auth_entry = next(e for e in result if "auth" in e.id)
        assert len(auth_entry.static.imports) > 0

    def test_parent_refs_to_mod(self):
        from kb_agent.views.file_view import FileViewBuilder
        from kb_agent.models.entry import KBEntry, StaticData

        nodes = [_make_node("a", path="src/auth.py")]
        mapper = ViewIDMapper(nodes, [])

        mod_entry = KBEntry(
            id="mod.src",
            layer=Layer.MOD,
            parent="arch.root",
            static=StaticData(
                kind=SymbolKind.MODULE, language=Language.PYTHON,
                path="src", line_start=0, line_end=0,
                files=["src/auth.py"],
            ),
        )
        builder = FileViewBuilder(mapper, llm=None)
        result = run(builder.build(edges=[], mod_entries=[mod_entry]))

        assert result[0].parent == "mod.src"


# ── MemViewBuilder Tests ────────────────────────────────────────


class TestMemView:
    def test_one_per_node(self):
        from kb_agent.views.mem_view import MemViewBuilder
        from kb_agent.models.entry import KBEntry, StaticData

        nodes = [
            _make_node("a", path="src/auth.py"),
            _make_node("b", path="src/auth.py"),
        ]
        mapper = ViewIDMapper(nodes, [])

        mod_entry = KBEntry(
            id="mod.src",
            layer=Layer.MOD,
            parent="arch.root",
            static=StaticData(
                kind=SymbolKind.MODULE, language=Language.PYTHON,
                path="src", line_start=0, line_end=0,
                files=["src/auth.py"],
            ),
        )

        builder = MemViewBuilder(mapper, llm=None)
        result = run(builder.build(nodes=nodes, edges=[], mod_entries=[mod_entry]))

        assert len(result) == 2
        assert all(e.layer == Layer.MEM for e in result)

    def test_backward_compat_ids(self):
        from kb_agent.views.mem_view import MemViewBuilder
        from kb_agent.models.entry import KBEntry, StaticData

        cls_node = _make_node("AuthService", kind=SymbolKind.CLASS, path="src/auth.py", line_start=5)
        method_node = _make_node("validate", kind=SymbolKind.FUNCTION, path="src/auth.py", line_start=10)
        contains_edge = _make_edge(cls_node.id, method_node.id, EdgeKind.CONTAINS, confidence=1.0)

        mapper = ViewIDMapper([cls_node, method_node], [contains_edge])

        mod_entry = KBEntry(
            id="mod.src",
            layer=Layer.MOD,
            parent="arch.root",
            static=StaticData(
                kind=SymbolKind.MODULE, language=Language.PYTHON,
                path="src", line_start=0, line_end=0,
                files=["src/auth.py"],
            ),
        )

        builder = MemViewBuilder(mapper, llm=None)
        result = run(builder.build(
            nodes=[cls_node, method_node], edges=[contains_edge], mod_entries=[mod_entry],
        ))

        # Check class entry ID format: mem.{module}.{file}.{name}_L{line}
        cls_entry = next(e for e in result if e.static.kind == SymbolKind.CLASS)
        assert cls_entry.id == "mem.src.auth.AuthService_L5"

        # Check method entry ID includes parent class name
        method_entry = next(e for e in result if e.static.kind == SymbolKind.FUNCTION)
        assert "authservice" in method_entry.id
        assert "_L10" in method_entry.id

    def test_parent_refs(self):
        from kb_agent.views.mem_view import MemViewBuilder
        from kb_agent.models.entry import KBEntry, StaticData

        nodes = [_make_node("a", path="src/auth.py")]
        mapper = ViewIDMapper(nodes, [])

        mod_entry = KBEntry(
            id="mod.src",
            layer=Layer.MOD,
            parent="arch.root",
            static=StaticData(
                kind=SymbolKind.MODULE, language=Language.PYTHON,
                path="src", line_start=0, line_end=0,
                files=["src/auth.py"],
            ),
        )

        builder = MemViewBuilder(mapper, llm=None)
        result = run(builder.build(nodes=nodes, edges=[], mod_entries=[mod_entry]))

        assert all(e.parent == "mod.src" for e in result)

    def test_outgoing_edges_in_imports(self):
        from kb_agent.views.mem_view import MemViewBuilder
        from kb_agent.models.entry import KBEntry, StaticData

        n1 = _make_node("a", path="src/auth.py")
        n2 = _make_node("b", path="src/user.py")
        call_edge = _make_edge(n1.id, n2.id, EdgeKind.IMPORTS)

        mapper = ViewIDMapper([n1, n2], [call_edge])
        mod_entry = KBEntry(
            id="mod.src",
            layer=Layer.MOD,
            parent="arch.root",
            static=StaticData(
                kind=SymbolKind.MODULE, language=Language.PYTHON,
                path="src", line_start=0, line_end=0,
                files=["src/auth.py"],
            ),
        )

        builder = MemViewBuilder(mapper, llm=None)
        result = run(builder.build(nodes=[n1], edges=[call_edge], mod_entries=[mod_entry]))

        assert "b" in result[0].static.imports
