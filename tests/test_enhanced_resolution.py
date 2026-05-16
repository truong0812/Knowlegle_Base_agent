"""Tests for enhanced symbol resolution (Phase 2, Step 1)."""
from __future__ import annotations

import pytest

from kb_agent.models.entry import Language, Parameter, SymbolKind
from kb_agent.models.graph import EdgeKind, SymbolEdge, SymbolNode
from kb_agent.graph.builder import GraphBuilder
from kb_agent.parser.base import AssignmentInfo, CallInfo, ImportInfo, ParseResult, SymbolInfo, TypeUsageInfo
from kb_agent.parser.python_parser import PythonParser


def _make_symbol(
    name: str = "func",
    kind: SymbolKind = SymbolKind.FUNCTION,
    line_start: int = 1,
    line_end: int = 10,
    parameters: list[Parameter] | None = None,
    return_type: str | None = None,
    children: list[SymbolInfo] | None = None,
    bases: list[str] | None = None,
    modifiers: list[str] | None = None,
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
        modifiers=modifiers or [],
    )


def _make_parse_result(
    file_path: str = "src/main.py",
    language: Language = Language.PYTHON,
    symbols: list[SymbolInfo] | None = None,
    imports: list[ImportInfo] | None = None,
    calls: list[CallInfo] | None = None,
    type_usages: list[TypeUsageInfo] | None = None,
    assignments: list[AssignmentInfo] | None = None,
) -> ParseResult:
    return ParseResult(
        file_path=file_path,
        language=language,
        symbols=symbols or [],
        imports=imports or [],
        calls=calls or [],
        type_usages=type_usages or [],
        assignments=assignments or [],
    )


class TestInheritedMethodResolution:
    def test_inherited_method_resolved(self):
        """self.validate() on a class that inherits validate from BaseService."""
        base_validate = _make_symbol("validate", kind=SymbolKind.FUNCTION, line_start=5, line_end=10)
        base_cls = _make_symbol(
            "BaseService", kind=SymbolKind.CLASS, line_start=1, line_end=12,
            children=[base_validate],
        )
        # Derived class has no own validate method — inherits from BaseService
        derived_do_work = _make_symbol("do_work", kind=SymbolKind.FUNCTION, line_start=20, line_end=30)
        derived_cls = _make_symbol(
            "AuthService", kind=SymbolKind.CLASS, line_start=15, line_end=35,
            children=[derived_do_work], bases=["BaseService"],
        )

        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "services/base.py": _make_parse_result(file_path="services/base.py", symbols=[base_cls]),
            "services/auth.py": _make_parse_result(
                file_path="services/auth.py",
                symbols=[derived_cls],
                calls=[CallInfo(
                    caller_name="do_work", callee_name="validate", line=25,
                    resolution_method="same_scope", is_self_call=True, receiver="self",
                    enclosing_class="AuthService",
                )],
            ),
        })

        calls = [e for e in builder.edges if e.kind == EdgeKind.CALLS]
        assert len(calls) == 1
        # Resolved via inheritance chain — uses inherited_scope resolution
        assert calls[0].resolution == "inherited_scope"
        assert calls[0].confidence == 0.80
        # Target should be BaseService.validate
        assert "BaseService" in calls[0].target
        assert "validate" in calls[0].target

    def test_own_method_not_redirected(self):
        """If the class has its own method, same_scope resolves to it directly."""
        method = _make_symbol("validate", kind=SymbolKind.FUNCTION, line_start=5, line_end=10)
        base_cls = _make_symbol(
            "BaseService", kind=SymbolKind.CLASS, line_start=1, line_end=12,
            children=[method],
        )
        derived_validate = _make_symbol("validate", kind=SymbolKind.FUNCTION, line_start=20, line_end=25)
        derived_do_work = _make_symbol("do_work", kind=SymbolKind.FUNCTION, line_start=30, line_end=40)
        derived_cls = _make_symbol(
            "AuthService", kind=SymbolKind.CLASS, line_start=15, line_end=45,
            children=[derived_validate, derived_do_work], bases=["BaseService"],
        )

        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "services/base.py": _make_parse_result(file_path="services/base.py", symbols=[base_cls]),
            "services/auth.py": _make_parse_result(
                file_path="services/auth.py",
                symbols=[derived_cls],
                calls=[CallInfo(
                    caller_name="do_work", callee_name="validate", line=35,
                    resolution_method="same_scope", is_self_call=True, receiver="self",
                    enclosing_class="AuthService",
                )],
            ),
        })

        calls = [e for e in builder.edges if e.kind == EdgeKind.CALLS]
        assert len(calls) == 1
        # Should stay as same_scope (found in immediate parent class AuthService)
        assert calls[0].resolution == "same_scope"
        assert "AuthService" in calls[0].target

    def test_multi_level_inheritance(self):
        """self.validate() resolved through 2 levels of inheritance."""
        base_method = _make_symbol("validate", kind=SymbolKind.FUNCTION, line_start=3, line_end=5)
        base_cls = _make_symbol(
            "BaseService", kind=SymbolKind.CLASS, line_start=1, line_end=7,
            children=[base_method],
        )
        mid_cls = _make_symbol(
            "Middleware", kind=SymbolKind.CLASS, line_start=10, line_end=15,
            bases=["BaseService"],
        )
        derived_method = _make_symbol("handle", kind=SymbolKind.FUNCTION, line_start=20, line_end=30)
        derived_cls = _make_symbol(
            "AuthService", kind=SymbolKind.CLASS, line_start=17, line_end=35,
            children=[derived_method], bases=["Middleware"],
        )

        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "base.py": _make_parse_result(file_path="base.py", symbols=[base_cls]),
            "mid.py": _make_parse_result(file_path="mid.py", symbols=[mid_cls]),
            "auth.py": _make_parse_result(
                file_path="auth.py",
                symbols=[derived_cls],
                calls=[CallInfo(
                    caller_name="handle", callee_name="validate", line=25,
                    resolution_method="same_scope", is_self_call=True, receiver="self",
                    enclosing_class="AuthService",
                )],
            ),
        })

        calls = [e for e in builder.edges if e.kind == EdgeKind.CALLS]
        assert len(calls) == 1
        assert calls[0].resolution == "inherited_scope"
        assert "BaseService" in calls[0].target


class TestDecoratorScopeResolution:
    def test_staticmethod_in_modifiers(self):
        """@staticmethod annotated method appears in modifiers."""
        method = _make_symbol(
            "create", kind=SymbolKind.FUNCTION, line_start=5, line_end=10,
            modifiers=["staticmethod"],
        )
        cls = _make_symbol(
            "Factory", kind=SymbolKind.CLASS, line_start=1, line_end=12,
            children=[method],
        )
        builder = GraphBuilder(repo_name="repo")
        builder.build({"src/factory.py": _make_parse_result(symbols=[cls])})

        # The modifier should be stored on the node
        factory_node = [n for n in builder.nodes if n.name == "create"][0]
        assert "staticmethod" in factory_node.modifiers

    def test_injected_method_confidence_lowered(self):
        """@inject decorated method gets lower confidence on edges targeting it."""
        injected_method = _make_symbol(
            "process", kind=SymbolKind.FUNCTION, line_start=5, line_end=10,
            modifiers=["injected"],
        )
        cls = _make_symbol(
            "Service", kind=SymbolKind.CLASS, line_start=1, line_end=12,
            children=[injected_method],
        )
        func = _make_symbol("handler", kind=SymbolKind.FUNCTION, line_start=15, line_end=25)

        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "src/svc.py": _make_parse_result(
                symbols=[cls, func],
                calls=[CallInfo(
                    caller_name="handler", callee_name="process", line=20,
                    resolution_method="same_file",
                )],
            ),
        })

        calls = [e for e in builder.edges if e.kind == EdgeKind.CALLS and "process" in e.target]
        assert len(calls) >= 1
        # Confidence should be capped at 0.50 for injected methods
        for call in calls:
            assert call.confidence <= 0.50

    def test_parsed_inject_decorator_is_normalized_and_capped(self):
        """Parsed @container.inject should become the canonical injected modifier."""
        source = b"""
class Service:
    @container.inject()
    def process(self):
        pass

def handler():
    process()
"""
        result = PythonParser().parse_file(source, "src/svc.py")
        service = next(sym for sym in result.symbols if sym.name == "Service")
        process = next(child for child in service.children if child.name == "process")
        assert "injected" in process.modifiers

        builder = GraphBuilder(repo_name="repo")
        builder.build({"src/svc.py": result})

        calls = [
            e for e in builder.edges
            if e.kind == EdgeKind.CALLS and "process" in e.target
        ]
        assert calls
        assert all(call.confidence <= 0.50 for call in calls)


class TestTypeInferenceResolution:
    def test_return_type_chain(self):
        """svc.login() where svc = get_service() -> AuthService."""
        auth_method = _make_symbol("login", kind=SymbolKind.FUNCTION, line_start=5, line_end=10)
        auth_cls = _make_symbol(
            "AuthService", kind=SymbolKind.CLASS, line_start=1, line_end=15,
            children=[auth_method],
        )
        get_svc = _make_symbol(
            "get_service", kind=SymbolKind.FUNCTION, line_start=20, line_end=30,
            return_type="AuthService",
        )
        handler = _make_symbol("handle", kind=SymbolKind.FUNCTION, line_start=35, line_end=50)

        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "src/main.py": _make_parse_result(
                symbols=[auth_cls, get_svc, handler],
                calls=[CallInfo(
                    caller_name="handle", callee_name="login", line=40,
                    resolution_method="dynamic_dispatch", receiver="svc",
                )],
                assignments=[AssignmentInfo(
                    variable_name="svc", callee_name="get_service", line=39,
                )],
            ),
        })

        calls = [e for e in builder.edges if e.kind == EdgeKind.CALLS]
        # Type inference requires receiver→assignment→return_type mapping which needs source analysis
        assert len(calls) == 1
        assert calls[0].resolution == "type_inferred"
        assert calls[0].confidence == 0.65
        assert "AuthService.login" in calls[0].target

    def test_type_inference_stays_inside_enclosing_function(self):
        """A receiver assignment in a different function should not leak scope."""
        auth_method = _make_symbol("login", kind=SymbolKind.FUNCTION, line_start=5, line_end=10)
        auth_cls = _make_symbol(
            "AuthService", kind=SymbolKind.CLASS, line_start=1, line_end=15,
            children=[auth_method],
        )
        get_svc = _make_symbol(
            "get_service", kind=SymbolKind.FUNCTION, line_start=20, line_end=25,
            return_type="AuthService",
        )
        setup = _make_symbol("setup", kind=SymbolKind.FUNCTION, line_start=30, line_end=35)
        handler = _make_symbol("handle", kind=SymbolKind.FUNCTION, line_start=40, line_end=50)

        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "src/main.py": _make_parse_result(
                symbols=[auth_cls, get_svc, setup, handler],
                calls=[CallInfo(
                    caller_name="handle", callee_name="login", line=45,
                    resolution_method="dynamic_dispatch", receiver="svc",
                )],
                assignments=[AssignmentInfo(
                    variable_name="svc", callee_name="get_service", line=32,
                )],
            ),
        })

        calls = [e for e in builder.edges if e.kind == EdgeKind.CALLS]
        assert calls == []

    def test_parser_to_builder_type_inferred_call(self):
        """Real parser output should resolve receiver calls via return type."""
        source = b"""
class AuthService:
    def login(self):
        pass

def get_service() -> AuthService:
    return AuthService()

def handle():
    svc = get_service()
    svc.login()
"""
        result = PythonParser().parse_file(source, "src/main.py")
        builder = GraphBuilder(repo_name="repo")
        builder.build({"src/main.py": result})

        calls = [
            e for e in builder.edges
            if e.kind == EdgeKind.CALLS and e.resolution == "type_inferred"
        ]
        assert len(calls) == 1
        assert "AuthService.login" in calls[0].target

    def test_no_false_positive_type_inference(self):
        """Return type of built-in types (str, int) should not create spurious edges."""
        func = _make_symbol(
            "get_name", kind=SymbolKind.FUNCTION, line_start=1, line_end=5,
            return_type="str",
        )
        handler = _make_symbol("handle", kind=SymbolKind.FUNCTION, line_start=10, line_end=20)

        builder = GraphBuilder(repo_name="repo")
        builder.build({
            "src/main.py": _make_parse_result(
                symbols=[func, handler],
                calls=[CallInfo(
                    caller_name="handle", callee_name="split", line=15,
                    resolution_method="dynamic_dispatch", receiver="name",
                )],
                assignments=[AssignmentInfo(
                    variable_name="name", callee_name="get_name", line=14,
                )],
            ),
        })

        calls = [e for e in builder.edges if e.kind == EdgeKind.CALLS]
        # No spurious edge to a non-existent "str" class
        assert len(calls) == 0


class TestResolutionConfidenceTable:
    def test_inherited_scope_confidence(self):
        """inherited_scope resolution should have confidence 0.80."""
        from kb_agent.graph.builder import RESOLUTION_CONFIDENCE
        assert RESOLUTION_CONFIDENCE["inherited_scope"] == 0.80

    def test_type_inferred_confidence(self):
        """type_inferred resolution should have confidence 0.65."""
        from kb_agent.graph.builder import RESOLUTION_CONFIDENCE
        assert RESOLUTION_CONFIDENCE["type_inferred"] == 0.65
