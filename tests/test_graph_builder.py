from __future__ import annotations

import pytest

from kb_agent.models.entry import Language, Parameter, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.graph.builder import GraphBuilder
from kb_agent.parser.base import CallInfo, ImportInfo, ParseResult, SymbolInfo, TypeUsageInfo


def _make_symbol(
    name: str = "func",
    kind: SymbolKind = SymbolKind.FUNCTION,
    line_start: int = 1,
    line_end: int = 10,
    parameters: list[Parameter] | None = None,
    return_type: str | None = None,
    children: list[SymbolInfo] | None = None,
    bases: list[str] | None = None,
) -> SymbolInfo:
    return SymbolInfo(
        name=name,
        kind=kind,
        line_start=line_start,
        line_end=line_end,
        signature=f"def {name}()",
        parameters=parameters or [],
        return_type=return_type,
        children=children or [],
        bases=bases or [],
    )


def _make_parse_result(
    file_path: str = "src/main.py",
    language: Language = Language.PYTHON,
    symbols: list[SymbolInfo] | None = None,
    imports: list[ImportInfo] | None = None,
    calls: list[CallInfo] | None = None,
    type_usages: list[TypeUsageInfo] | None = None,
) -> ParseResult:
    return ParseResult(
        file_path=file_path,
        language=language,
        symbols=symbols or [],
        imports=imports or [],
        calls=calls or [],
        type_usages=type_usages or [],
    )


class TestNodeId:
    def test_top_level_function(self):
        sym = _make_symbol("login", parameters=[
            Parameter(name="email", type="str"),
            Parameter(name="password", type="str"),
        ])
        builder = GraphBuilder(repo_name="repo")
        builder.build({"src/auth.py": _make_parse_result(symbols=[sym])})
        assert builder.nodes[0].id == "repo/src/auth.py::login(str, str)"

    def test_method_in_class(self):
        method = _make_symbol("validate", kind=SymbolKind.FUNCTION, line_start=5, line_end=15)
        cls = _make_symbol(
            "AuthMiddleware", kind=SymbolKind.CLASS, line_start=1, line_end=20,
            children=[method],
        )
        builder = GraphBuilder(repo_name="repo")
        builder.build({"src/auth.py": _make_parse_result(symbols=[cls])})
        assert builder.nodes[1].id == "repo/src/auth.py::AuthMiddleware.validate()"

    def test_overload_dedup(self):
        sym1 = _make_symbol("process", line_start=10, line_end=20, parameters=[
            Parameter(name="data", type="dict"),
        ])
        sym2 = _make_symbol("process", line_start=25, line_end=35, parameters=[
            Parameter(name="data", type="str"),
        ])
        builder = GraphBuilder(repo_name="repo")
        builder.build({"src/h.py": _make_parse_result(symbols=[sym1, sym2])})
        ids = [n.id for n in builder.nodes]
        assert ids[0] == "repo/src/h.py::process(dict)"
        assert ids[1] == "repo/src/h.py::process(str)"

    def test_same_signature_dedup(self):
        sym1 = _make_symbol("process", line_start=10, parameters=[
            Parameter(name="x", type="int"),
        ])
        sym2 = _make_symbol("process", line_start=20, parameters=[
            Parameter(name="y", type="int"),
        ])
        builder = GraphBuilder(repo_name="repo")
        builder.build({"src/h.py": _make_parse_result(symbols=[sym1, sym2])})
        ids = [n.id for n in builder.nodes]
        assert "#L20" in ids[1]


class TestContainsEdge:
    def test_class_to_method(self):
        method = _make_symbol("do_work", kind=SymbolKind.FUNCTION, line_start=5, line_end=10)
        cls = _make_symbol("Worker", kind=SymbolKind.CLASS, line_start=1, line_end=12, children=[method])
        builder = GraphBuilder(repo_name="repo")
        builder.build({"src/worker.py": _make_parse_result(symbols=[cls])})

        contains = [e for e in builder.edges if e.kind == EdgeKind.CONTAINS]
        assert len(contains) == 1
        assert contains[0].confidence == 1.0
        assert "Worker" in contains[0].source
        assert "do_work" in contains[0].target


class TestImportsEdge:
    def test_resolved_import(self):
        sym_b = _make_symbol("helper", kind=SymbolKind.FUNCTION, line_start=1, line_end=5)
        sym_a = _make_symbol("main_func", kind=SymbolKind.FUNCTION, line_start=1, line_end=10)
        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "src/utils.py": _make_parse_result(file_path="src/utils.py", symbols=[sym_b]),
            "src/main.py": _make_parse_result(
                file_path="src/main.py",
                symbols=[sym_a],
                imports=[ImportInfo(module_path="src.utils", imported_names=["helper"])],
            ),
        })

        imports = [e for e in builder.edges if e.kind == EdgeKind.IMPORTS]
        assert len(imports) == 1
        assert imports[0].confidence == 0.95


class TestCallsEdges:
    def test_same_scope_self_call(self):
        method = _make_symbol("do_work", kind=SymbolKind.FUNCTION, line_start=5, line_end=15)
        cls = _make_symbol(
            "Worker", kind=SymbolKind.CLASS, line_start=1, line_end=20,
            children=[method],
        )
        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "src/worker.py": _make_parse_result(
                symbols=[cls],
                calls=[CallInfo(
                    caller_name="do_work", callee_name="do_work", line=10,
                    resolution_method="same_scope", is_self_call=True, receiver="self",
                )],
            ),
        })

        calls = [e for e in builder.edges if e.kind == EdgeKind.CALLS]
        assert len(calls) == 1
        assert calls[0].confidence == 0.85
        assert calls[0].resolution == "same_scope"

    def test_constructor_call(self):
        cls = _make_symbol("User", kind=SymbolKind.CLASS, line_start=1, line_end=10)
        func = _make_symbol("create", kind=SymbolKind.FUNCTION, line_start=15, line_end=30)
        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "src/main.py": _make_parse_result(
                symbols=[cls, func],
                calls=[CallInfo(
                    caller_name="create", callee_name="User", line=20,
                    resolution_method="constructor",
                )],
            ),
        })

        calls = [e for e in builder.edges if e.kind == EdgeKind.CALLS]
        assert len(calls) == 1
        assert calls[0].confidence == 0.75
        assert calls[0].resolution == "constructor"

    def test_dynamic_dispatch_skipped(self):
        func = _make_symbol("handler", kind=SymbolKind.FUNCTION, line_start=1, line_end=10)
        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "src/main.py": _make_parse_result(
                symbols=[func],
                calls=[CallInfo(
                    caller_name="handler", callee_name="method", line=5,
                    resolution_method="dynamic_dispatch", receiver="obj",
                )],
            ),
        })

        calls = [e for e in builder.edges if e.kind == EdgeKind.CALLS]
        assert len(calls) == 0  # confidence 0.35 < 0.50 threshold

    def test_unresolved_skipped(self):
        func = _make_symbol("handler", kind=SymbolKind.FUNCTION, line_start=1, line_end=10)
        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "src/main.py": _make_parse_result(
                symbols=[func],
                calls=[CallInfo(
                    caller_name="handler", callee_name="unknown_func", line=5,
                    resolution_method="unresolved",
                )],
            ),
        })

        calls = [e for e in builder.edges if e.kind == EdgeKind.CALLS]
        assert len(calls) == 0

    def test_unresolved_upgraded_to_direct_import(self):
        func_a = _make_symbol("process", kind=SymbolKind.FUNCTION, line_start=1, line_end=10)
        func_b = _make_symbol("helper", kind=SymbolKind.FUNCTION, line_start=1, line_end=5)
        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "src/utils.py": _make_parse_result(file_path="src/utils.py", symbols=[func_b]),
            "src/main.py": _make_parse_result(
                file_path="src/main.py",
                symbols=[func_a],
                imports=[ImportInfo(module_path="src.utils", imported_names=["helper"])],
                calls=[CallInfo(
                    caller_name="process", callee_name="helper", line=5,
                    resolution_method="unresolved",
                )],
            ),
        })

        calls = [e for e in builder.edges if e.kind == EdgeKind.CALLS]
        assert len(calls) == 1
        assert calls[0].resolution == "direct_import"
        assert calls[0].confidence == 0.75


class TestInheritsEdge:
    def test_base_class(self):
        parent = _make_symbol("Base", kind=SymbolKind.CLASS, line_start=1, line_end=10)
        child = _make_symbol(
            "Derived", kind=SymbolKind.CLASS, line_start=15, line_end=30,
            bases=["Base"],
        )
        builder = GraphBuilder(repo_name="repo")
        builder.build({"src/cls.py": _make_parse_result(symbols=[parent, child])})

        inherits = [e for e in builder.edges if e.kind == EdgeKind.INHERITS]
        assert len(inherits) == 1
        assert inherits[0].confidence == 0.95
        assert "Derived" in inherits[0].source
        assert "Base" in inherits[0].target


class TestUsesTypeEdge:
    def test_return_type_usage(self):
        user_cls = _make_symbol("User", kind=SymbolKind.CLASS, line_start=1, line_end=10)
        func = _make_symbol("get_user", kind=SymbolKind.FUNCTION, line_start=15, line_end=25, return_type="User")
        builder = GraphBuilder(repo_name="repo")
        builder.build({"src/main.py": _make_parse_result(
            symbols=[user_cls, func],
            type_usages=[TypeUsageInfo(
                symbol_name="get_user", type_name="User",
                usage_context="return_type", line=15,
            )],
        )})

        uses = [e for e in builder.edges if e.kind == EdgeKind.USES_TYPE]
        assert len(uses) == 1
        assert uses[0].confidence == 0.80


class TestFullBuild:
    def test_multi_file_build(self):
        user_cls = _make_symbol("User", kind=SymbolKind.CLASS, line_start=1, line_end=15)
        auth_method = _make_symbol("validate", kind=SymbolKind.FUNCTION, line_start=5, line_end=12)
        auth_cls = _make_symbol(
            "AuthService", kind=SymbolKind.CLASS, line_start=1, line_end=20,
            children=[auth_method], bases=["BaseService"],
        )
        base_cls = _make_symbol("BaseService", kind=SymbolKind.CLASS, line_start=1, line_end=5)

        builder = GraphBuilder(repo_name="myapp")
        builder.build({
            "models/user.py": _make_parse_result(
                file_path="models/user.py", symbols=[user_cls],
            ),
            "services/auth.py": _make_parse_result(
                file_path="services/auth.py", symbols=[auth_cls],
                imports=[ImportInfo(module_path="models.user", imported_names=["User"])],
                calls=[CallInfo(
                    caller_name="validate", callee_name="User", line=10,
                    resolution_method="constructor",
                )],
                type_usages=[TypeUsageInfo(
                    symbol_name="validate", type_name="User",
                    usage_context="return_type", line=5,
                )],
            ),
            "services/base.py": _make_parse_result(
                file_path="services/base.py", symbols=[base_cls],
            ),
        })

        assert len(builder.nodes) == 4  # User, AuthService, validate, BaseService
        edge_kinds = {e.kind for e in builder.edges}
        assert EdgeKind.CONTAINS in edge_kinds
        assert EdgeKind.CALLS in edge_kinds
        assert EdgeKind.USES_TYPE in edge_kinds
        assert EdgeKind.INHERITS in edge_kinds
