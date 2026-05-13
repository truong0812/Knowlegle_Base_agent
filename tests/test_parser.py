from __future__ import annotations

from kb_agent.models.entry import Language, SymbolKind
from kb_agent.parser.factory import get_parser


class TestPythonParser:
    def test_parse_extracts_classes(self, sample_python_source: bytes):
        parser = get_parser(Language.PYTHON)
        result = parser.parse_file(sample_python_source, "user_service.py")
        classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
        assert len(classes) == 1
        assert classes[0].name == "UserService"
        assert classes[0].docstring is not None

    def test_parse_extracts_class_methods(self, sample_python_source: bytes):
        parser = get_parser(Language.PYTHON)
        result = parser.parse_file(sample_python_source, "user_service.py")
        cls = [s for s in result.symbols if s.kind == SymbolKind.CLASS][0]
        method_names = {m.name for m in cls.children}
        assert "create_user" in method_names
        assert "get_user" in method_names

    def test_parse_extracts_functions(self, sample_python_source: bytes):
        parser = get_parser(Language.PYTHON)
        result = parser.parse_file(sample_python_source, "user_service.py")
        funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION]
        func_names = {f.name for f in funcs}
        assert "validate_email" in func_names
        assert "format_user_display" in func_names

    def test_parse_extracts_parameters(self, sample_python_source: bytes):
        parser = get_parser(Language.PYTHON)
        result = parser.parse_file(sample_python_source, "user_service.py")
        cls = [s for s in result.symbols if s.kind == SymbolKind.CLASS][0]
        create = [m for m in cls.children if m.name == "create_user"][0]
        assert len(create.parameters) == 2
        assert create.parameters[0].name == "name"
        assert create.parameters[0].type == "str"

    def test_parse_extracts_imports(self, sample_python_source: bytes):
        parser = get_parser(Language.PYTHON)
        result = parser.parse_file(sample_python_source, "user_service.py")
        assert len(result.imports) > 0
        mod_paths = [i.module_path for i in result.imports]
        assert "os" in mod_paths
        assert "typing" in mod_paths

    def test_parse_extracts_return_type(self, sample_python_source: bytes):
        parser = get_parser(Language.PYTHON)
        result = parser.parse_file(sample_python_source, "user_service.py")
        cls = [s for s in result.symbols if s.kind == SymbolKind.CLASS][0]
        get = [m for m in cls.children if m.name == "get_user"][0]
        assert get.return_type is not None

    def test_parse_extracts_docstring(self, sample_python_source: bytes):
        parser = get_parser(Language.PYTHON)
        result = parser.parse_file(sample_python_source, "user_service.py")
        cls = [s for s in result.symbols if s.kind == SymbolKind.CLASS][0]
        create = [m for m in cls.children if m.name == "create_user"][0]
        assert create.docstring is not None

    def test_parse_no_errors(self, sample_python_source: bytes):
        parser = get_parser(Language.PYTHON)
        result = parser.parse_file(sample_python_source, "user_service.py")
        assert result.errors == []


class TestCSharpParser:
    def test_parse_extracts_classes(self, sample_csharp_source: bytes):
        parser = get_parser(Language.CSHARP)
        result = parser.parse_file(sample_csharp_source, "UserService.cs")
        classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
        class_names = {c.name for c in classes}
        assert "UserService" in class_names
        assert "User" in class_names

    def test_parse_extracts_methods(self, sample_csharp_source: bytes):
        parser = get_parser(Language.CSHARP)
        result = parser.parse_file(sample_csharp_source, "UserService.cs")
        svc = [s for s in result.symbols if s.name == "UserService"][0]
        method_names = {m.name for m in svc.children if m.kind == SymbolKind.METHOD}
        assert "CreateUser" in method_names
        assert "GetUser" in method_names

    def test_parse_extracts_properties(self, sample_csharp_source: bytes):
        parser = get_parser(Language.CSHARP)
        result = parser.parse_file(sample_csharp_source, "UserService.cs")
        user = [s for s in result.symbols if s.name == "User"][0]
        props = [c for c in user.children if c.kind == SymbolKind.PROPERTY]
        assert len(props) >= 2
        prop_names = {p.name for p in props}
        assert "Name" in prop_names
        assert "Email" in prop_names

    def test_parse_extracts_usings(self, sample_csharp_source: bytes):
        parser = get_parser(Language.CSHARP)
        result = parser.parse_file(sample_csharp_source, "UserService.cs")
        assert len(result.imports) >= 1
        mod_paths = [i.module_path for i in result.imports]
        assert any("System" in p for p in mod_paths)

    def test_parse_extracts_modifiers(self, sample_csharp_source: bytes):
        parser = get_parser(Language.CSHARP)
        result = parser.parse_file(sample_csharp_source, "UserService.cs")
        svc = [s for s in result.symbols if s.name == "UserService"][0]
        assert "public" in svc.modifiers

    def test_parse_no_errors(self, sample_csharp_source: bytes):
        parser = get_parser(Language.CSHARP)
        result = parser.parse_file(sample_csharp_source, "UserService.cs")
        assert result.errors == []


class TestCppParser:
    def test_parse_extracts_classes(self, sample_cpp_source: bytes):
        parser = get_parser(Language.CPP)
        result = parser.parse_file(sample_cpp_source, "user_service.cpp")
        classes = [s for s in result.symbols if s.kind == SymbolKind.CLASS]
        class_names = {c.name for c in classes}
        assert "User" in class_names
        assert "UserService" in class_names

    def test_parse_extracts_methods(self, sample_cpp_source: bytes):
        parser = get_parser(Language.CPP)
        result = parser.parse_file(sample_cpp_source, "user_service.cpp")
        svc = [s for s in result.symbols if s.name == "UserService"][0]
        method_names = {m.name for m in svc.children if m.kind == SymbolKind.FUNCTION}
        assert "create_user" in method_names
        assert "get_user" in method_names

    def test_parse_extracts_free_functions(self, sample_cpp_source: bytes):
        parser = get_parser(Language.CPP)
        result = parser.parse_file(sample_cpp_source, "user_service.cpp")
        funcs = [s for s in result.symbols if s.kind == SymbolKind.FUNCTION and not s.children]
        func_names = {f.name for f in funcs}
        assert "validate_email" in func_names

    def test_parse_extracts_includes(self, sample_cpp_source: bytes):
        parser = get_parser(Language.CPP)
        result = parser.parse_file(sample_cpp_source, "user_service.cpp")
        assert len(result.imports) >= 2
        mod_paths = [i.module_path for i in result.imports]
        assert "string" in mod_paths

    def test_parse_no_errors(self, sample_cpp_source: bytes):
        parser = get_parser(Language.CPP)
        result = parser.parse_file(sample_cpp_source, "user_service.cpp")
        assert result.errors == []
