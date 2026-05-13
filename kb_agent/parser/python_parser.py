from __future__ import annotations

import ast
from typing import Sequence

import tree_sitter_python as tspython
from tree_sitter import Language as TSLanguage, Parser, Node

from kb_agent.models.entry import Language, Parameter, SymbolKind
from kb_agent.parser.base import BaseParser, ImportInfo, ParseResult, SymbolInfo


class PythonParser(BaseParser):
    def __init__(self) -> None:
        self._language = TSLanguage(tspython.language())
        self._parser = Parser(self._language)

    def parse_file(self, source: bytes, file_path: str) -> ParseResult:
        errors: list[str] = []
        tree = self._parser.parse(source)

        if tree.root_node.has_error:
            # Fallback to built-in ast module
            try:
                return self._fallback_ast_parse(source, file_path)
            except SyntaxError as e:
                errors.append(f"Parse error: {e}")
                return ParseResult(
                    file_path=file_path, language=Language.PYTHON, errors=errors
                )

        symbols = self.extract_symbols(tree.root_node)
        imports = self.extract_imports(tree.root_node)
        return ParseResult(
            file_path=file_path,
            language=Language.PYTHON,
            symbols=symbols,
            imports=imports,
            errors=errors,
        )

    def extract_symbols(self, root_node: Node) -> list[SymbolInfo]:
        symbols: list[SymbolInfo] = []
        self._walk_for_symbols(root_node, symbols)
        return symbols

    def _walk_for_symbols(self, node: Node, out: list[SymbolInfo], depth: int = 0) -> None:
        for child in node.children:
            if child.type == "class_definition":
                out.append(self._extract_class(child))
            elif child.type == "function_definition":
                out.append(self._extract_function(child))
            elif child.type == "decorated_definition":
                target = child.children[-1]
                if target.type == "class_definition":
                    sym = self._extract_class(target)
                    sym.modifiers.append("decorated")
                    out.append(sym)
                elif target.type == "function_definition":
                    sym = self._extract_function(target)
                    sym.modifiers.append("decorated")
                    out.append(sym)
            # Recurse into class bodies but limit depth
            if depth < 2 and child.type in ("module", "block", "class_definition"):
                self._walk_for_symbols(child, out, depth + 1)

    def _extract_class(self, node: Node) -> SymbolInfo:
        name = self._get_child_by_type(node, "identifier")
        name_str = self._node_text(name) if name else "<unknown>"

        # Extract methods from class body
        children: list[SymbolInfo] = []
        body = self._get_child_by_type(node, "block")
        if body:
            for child in body.children:
                if child.type == "function_definition":
                    children.append(self._extract_function(child))
                elif child.type == "decorated_definition":
                    target = child.children[-1]
                    if target.type == "function_definition":
                        fn = self._extract_function(target)
                        fn.modifiers.append("decorated")
                        children.append(fn)

        docstring = self._extract_docstring(body) if body else None

        return SymbolInfo(
            name=name_str,
            kind=SymbolKind.CLASS,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=f"class {name_str}",
            docstring=docstring,
            children=children,
        )

    def _extract_function(self, node: Node) -> SymbolInfo:
        name = self._get_child_by_type(node, "identifier")
        name_str = self._node_text(name) if name else "<unknown>"

        params = self._extract_parameters(node)
        return_type = self._get_child_by_type(node, "type")
        return_type_str = self._node_text(return_type) if return_type else None

        body = self._get_child_by_type(node, "block")
        docstring = self._extract_docstring(body) if body else None

        modifiers: list[str] = []
        if name_str.startswith("_") and not name_str.startswith("__"):
            modifiers.append("private")

        # Filter 'self' and 'cls' from parameters for class methods
        params = [p for p in params if p.name not in ("self", "cls")]

        sig = f"def {name_str}({', '.join(self._format_param(p) for p in params)})"
        if return_type_str:
            sig += f" -> {return_type_str}"

        return SymbolInfo(
            name=name_str,
            kind=SymbolKind.FUNCTION,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=sig,
            parameters=params,
            return_type=return_type_str,
            modifiers=modifiers,
            docstring=docstring,
        )

    def _extract_parameters(self, node: Node) -> list[Parameter]:
        params_node = self._get_child_by_type(node, "parameters")
        if not params_node:
            return []
        result: list[Parameter] = []
        for child in params_node.children:
            if child.type == "identifier":
                result.append(Parameter(name=self._node_text(child)))
            elif child.type == "typed_parameter":
                ident = self._get_child_by_type(child, "identifier")
                type_node = self._get_child_by_type(child, "type")
                result.append(
                    Parameter(
                        name=self._node_text(ident) if ident else "?",
                        type=self._node_text(type_node) if type_node else None,
                    )
                )
            elif child.type == "default_parameter":
                ident = self._get_child_by_type(child, "identifier")
                result.append(
                    Parameter(name=self._node_text(ident) if ident else "?")
                )
            elif child.type == "typed_default_parameter":
                ident = self._get_child_by_type(child, "identifier")
                type_node = self._get_child_by_type(child, "type")
                result.append(
                    Parameter(
                        name=self._node_text(ident) if ident else "?",
                        type=self._node_text(type_node) if type_node else None,
                    )
                )
        return result

    def _extract_docstring(self, body_node: Node) -> str | None:
        if not body_node or not body_node.children:
            return None
        first = body_node.children[0]
        if first.type == "expression_statement":
            expr = first.children[0] if first.children else None
            if expr and expr.type == "string":
                text = self._node_text(expr)
                return text.strip("\"'").strip()
        return None

    def extract_imports(self, root_node: Node) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        self._walk_for_imports(root_node, imports)
        return imports

    def _walk_for_imports(self, node: Node, out: list[ImportInfo]) -> None:
        for child in node.children:
            if child.type == "import_statement":
                names = [self._node_text(n) for n in child.children_by_field_name("name")]
                if names:
                    out.append(ImportInfo(module_path=names[0], imported_names=names))
                else:
                    # Fallback: extract identifiers after 'import' keyword
                    parts = [c for c in child.children if c.type == "dotted_name" or c.type == "identifier"]
                    for p in parts:
                        out.append(ImportInfo(module_path=self._node_text(p)))
            elif child.type == "import_from_statement":
                module = self._get_child_by_type(child, "dotted_name")
                mod_str = self._node_text(module) if module else ""
                names: list[str] = []
                for c in child.children:
                    if c.type == "dotted_name" and c != module:
                        names.append(self._node_text(c))
                    elif c.type == "identifier" and not names and c.prev_sibling and self._node_text(c.prev_sibling) == "from":
                        continue
                    elif c.type == "identifier":
                        names.append(self._node_text(c))
                out.append(ImportInfo(module_path=mod_str, imported_names=names))
            # Don't recurse into class/function bodies for imports

    def _fallback_ast_parse(self, source: bytes, file_path: str) -> ParseResult:
        tree = ast.parse(source.decode("utf-8"))
        symbols: list[SymbolInfo] = []
        imports: list[ImportInfo] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                children = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        children.append(self._ast_func_to_symbol(item))
                docstring = ast.get_docstring(node)
                symbols.append(
                    SymbolInfo(
                        name=node.name,
                        kind=SymbolKind.CLASS,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        signature=f"class {node.name}",
                        docstring=docstring,
                        children=children,
                    )
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Only top-level functions (not inside class — handled above)
                if not isinstance(getattr(node, "_parent", None), ast.ClassDef):
                    symbols.append(self._ast_func_to_symbol(node))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(ImportInfo(module_path=alias.name))
            elif isinstance(node, ast.ImportFrom):
                imports.append(
                    ImportInfo(
                        module_path=node.module or "",
                        imported_names=[a.name for a in node.names],
                    )
                )

        return ParseResult(
            file_path=file_path, language=Language.PYTHON, symbols=symbols, imports=imports
        )

    def _ast_func_to_symbol(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> SymbolInfo:
        params = []
        for arg in node.args.args:
            p = Parameter(name=arg.arg)
            if arg.annotation:
                p.type = ast.unparse(arg.annotation)
            params.append(p)

        ret = ast.unparse(node.returns) if node.returns else None
        docstring = ast.get_docstring(node)
        modifiers = ["async"] if isinstance(node, ast.AsyncFunctionDef) else []
        if node.name.startswith("_") and not node.name.startswith("__"):
            modifiers.append("private")

        sig = f"def {node.name}({', '.join(self._format_param(p) for p in params)})"
        if ret:
            sig += f" -> {ret}"

        return SymbolInfo(
            name=node.name,
            kind=SymbolKind.FUNCTION,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            signature=sig,
            parameters=params,
            return_type=ret,
            modifiers=modifiers,
            docstring=docstring,
        )

    @staticmethod
    def _format_param(p: Parameter) -> str:
        if p.type:
            return f"{p.name}: {p.type}"
        return p.name

    def _get_child_by_type(self, node: Node, type_name: str) -> Node | None:
        for child in node.children:
            if child.type == type_name:
                return child
        return None
