from __future__ import annotations

import tree_sitter_cpp as tscpp
from tree_sitter import Language as TSLanguage, Parser, Node

from kb_agent.models.entry import Language, Parameter, SymbolKind
from kb_agent.parser.base import BaseParser, ImportInfo, ParseResult, SymbolInfo


class CppParser(BaseParser):
    def __init__(self) -> None:
        self._language = TSLanguage(tscpp.language())
        self._parser = Parser(self._language)

    def parse_file(self, source: bytes, file_path: str) -> ParseResult:
        errors: list[str] = []
        tree = self._parser.parse(source)

        symbols = self.extract_symbols(tree.root_node)
        imports = self.extract_imports(tree.root_node)
        return ParseResult(
            file_path=file_path,
            language=Language.CPP,
            symbols=symbols,
            imports=imports,
            errors=errors,
        )

    def extract_symbols(self, root_node: Node) -> list[SymbolInfo]:
        symbols: list[SymbolInfo] = []
        self._walk(root_node, symbols, depth=0)
        return symbols

    def _walk(self, node: Node, out: list[SymbolInfo], depth: int) -> None:
        for child in node.children:
            if child.type == "namespace_definition":
                self._walk(child, out, depth)
            elif child.type == "class_specifier":
                out.append(self._extract_class(child))
            elif child.type == "struct_specifier":
                out.append(self._extract_class(child, kind=SymbolKind.STRUCT))
            elif child.type == "function_definition":
                sym = self._extract_function(child)
                if sym:
                    out.append(sym)
            elif child.type == "declaration":
                # May contain function declaration
                decl = self._try_extract_declaration(child)
                if decl:
                    out.append(decl)
            elif child.type == "template_declaration":
                # Extract the inner class/function from template
                for inner in child.children:
                    if inner.type == "class_specifier":
                        out.append(self._extract_class(inner, template=True))
                    elif inner.type == "function_definition":
                        sym = self._extract_function(inner, template=True)
                        if sym:
                            sym.modifiers.append("template")
                            out.append(sym)
            elif depth < 4:
                self._walk(child, out, depth + 1)

    def _extract_class(self, node: Node, kind: SymbolKind = SymbolKind.CLASS, template: bool = False) -> SymbolInfo:
        name = node.child_by_field_name("name")
        name_str = self._node_text(name) if name else "<unknown>"

        children: list[SymbolInfo] = []
        body = self._get_field_body(node)
        if body:
            for child in body.children:
                if child.type == "function_definition":
                    sym = self._extract_function(child)
                    if sym:
                        children.append(sym)
                elif child.type == "declaration":
                    decl = self._try_extract_declaration(child)
                    if decl and decl.kind == SymbolKind.FUNCTION:
                        children.append(decl)
                elif child.type == "access_specifier":
                    pass  # skip

        keyword = "struct" if kind == SymbolKind.STRUCT else "class"
        prefix = "template " if template else ""
        sig = f"{prefix}{keyword} {name_str}"

        return SymbolInfo(
            name=name_str,
            kind=kind,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=sig,
            modifiers=["template"] if template else [],
            children=children,
        )

    def _extract_function(self, node: Node, template: bool = False) -> SymbolInfo | None:
        # function_definition has: type + declarator + body
        decl = node.child_by_field_name("declarator")
        if not decl:
            # Try first child that is a function_declarator
            for child in node.children:
                if child.type == "function_declarator":
                    decl = child
                    break
        if not decl:
            return None

        name = self._extract_declarator_name(decl)
        params = self._extract_parameters(decl)

        # Return type is in the type field of the parent function_definition
        ret_type = node.child_by_field_name("type")
        ret_str = self._node_text(ret_type) if ret_type else None

        # Detect if this is a constructor (name matches class, no return type)
        kind = SymbolKind.FUNCTION
        modifiers: list[str] = []
        if template:
            modifiers.append("template")

        sig = f"{name}({', '.join(self._format_param(p) for p in params)})"
        if ret_str and not name.startswith("~"):
            sig = f"{ret_str} {sig}"

        return SymbolInfo(
            name=name,
            kind=kind,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=sig,
            parameters=params,
            return_type=ret_str,
            modifiers=modifiers,
        )

    def _try_extract_declaration(self, node: Node) -> SymbolInfo | None:
        # Simple function declarations
        decl = node.child_by_field_name("declarator")
        if decl and decl.type == "function_declarator":
            name = self._extract_declarator_name(decl)
            params = self._extract_parameters(decl)
            ret_type = node.child_by_field_name("type")
            ret_str = self._node_text(ret_type) if ret_type else None
            sig = f"{name}({', '.join(self._format_param(p) for p in params)})"
            if ret_str:
                sig = f"{ret_str} {sig}"
            return SymbolInfo(
                name=name,
                kind=SymbolKind.FUNCTION,
                line_start=node.start_point[0] + 1,
                line_end=node.end_point[0] + 1,
                signature=sig,
                parameters=params,
                return_type=ret_str,
            )
        return None

    def _extract_declarator_name(self, decl: Node) -> str:
        name = decl.child_by_field_name("name")
        if name:
            return self._node_text(name)
        # Qualified name (e.g., MyClass::method)
        for child in decl.children:
            if child.type == "qualified_identifier":
                scope = child.child_by_field_name("scope")
                name_part = child.child_by_field_name("name")
                parts = []
                if scope:
                    parts.append(self._node_text(scope))
                if name_part:
                    parts.append(self._node_text(name_part))
                return "::".join(parts) if parts else self._node_text(child)
            if child.type == "identifier" or child.type == "field_identifier":
                return self._node_text(child)
        # Fallback: first identifier child
        for child in decl.children:
            if "identifier" in child.type:
                return self._node_text(child)
        return "<unknown>"

    def _extract_parameters(self, decl: Node) -> list[Parameter]:
        params_node = decl.child_by_field_name("parameters")
        if not params_node:
            return []
        result: list[Parameter] = []
        for child in params_node.children:
            if child.type == "parameter_declaration":
                p_type = child.child_by_field_name("type")
                p_decl = child.child_by_field_name("declarator")
                # Handle reference types like "const std::string&"
                type_str = self._node_text(p_type) if p_type else None
                name_str = None
                if p_decl:
                    name_str = self._extract_declarator_name(p_decl)
                    # Check for reference/pointer in declarator
                    decl_text = self._node_text(p_decl)
                    if "&" in decl_text and type_str and "&" not in type_str:
                        type_str = type_str + "&"
                result.append(
                    Parameter(
                        name=name_str or "?",
                        type=type_str,
                    )
                )
        return result

    def extract_imports(self, root_node: Node) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        self._walk_for_includes(root_node, imports)
        return imports

    def _walk_for_includes(self, node: Node, out: list[ImportInfo]) -> None:
        for child in node.children:
            if child.type == "preproc_include":
                path_node = child.child_by_field_name("path")
                if path_node:
                    path_str = self._node_text(path_node).strip('"<>')
                    out.append(ImportInfo(module_path=path_str))
            elif child.type == "namespace_definition":
                # Don't recurse into namespaces for includes
                pass

    def _get_field_body(self, node: Node) -> Node | None:
        for child in node.children:
            if child.type == "field_declaration_list":
                return child
        return None

    @staticmethod
    def _format_param(p: Parameter) -> str:
        if p.type and p.name and p.name != "?":
            return f"{p.type} {p.name}"
        if p.type:
            return p.type
        return p.name or "?"
