from __future__ import annotations

import tree_sitter_cpp as tscpp
from tree_sitter import Language as TSLanguage, Parser, Node

from kb_agent.models.entry import Language, Parameter, SymbolKind
from kb_agent.parser.base import BaseParser, CallInfo, ImportInfo, ParseResult, SymbolInfo, TypeUsageInfo


class CppParser(BaseParser):
    def __init__(self) -> None:
        self._language = TSLanguage(tscpp.language())
        self._parser = Parser(self._language)

    def parse_file(self, source: bytes, file_path: str) -> ParseResult:
        errors: list[str] = []
        tree = self._parser.parse(source)

        symbols = self.extract_symbols(tree.root_node)
        imports = self.extract_imports(tree.root_node)
        calls = self._extract_calls(tree.root_node, symbols)
        type_usages = self._extract_type_usages(symbols)
        return ParseResult(
            file_path=file_path,
            language=Language.CPP,
            symbols=symbols,
            imports=imports,
            calls=calls,
            type_usages=type_usages,
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

        # Extract base classes from base_class_clause
        bases: list[str] = []
        # Base class clause is a sibling of the class specifier, not a child
        # Check parent's children for base_class_clause
        parent = node.parent
        if parent:
            for child in parent.children:
                if child.type == "base_class_clause":
                    for bc in child.children:
                        if bc.type in ("type_identifier", "qualified_identifier"):
                            bases.append(self._node_text(bc))

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
            bases=bases,
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

    def _extract_calls(self, root_node: Node, symbols: list[SymbolInfo]) -> list[CallInfo]:
        """Walk AST for call_expression nodes."""
        class_names = {s.name for s in symbols if s.kind in (SymbolKind.CLASS, SymbolKind.STRUCT)}
        local_func_names: set[str] = set()
        for s in symbols:
            if s.kind == SymbolKind.FUNCTION:
                local_func_names.add(s.name)
            for c in s.children:
                if c.kind == SymbolKind.FUNCTION:
                    local_func_names.add(c.name)

        calls: list[CallInfo] = []
        self._walk_for_calls(root_node, calls, class_names, local_func_names)
        return calls

    def _walk_for_calls(
        self, node: Node, out: list[CallInfo],
        class_names: set[str], local_names: set[str],
    ) -> None:
        for child in node.children:
            if child.type == "call_expression":
                call_info = self._resolve_cpp_call(child, class_names, local_names)
                if call_info:
                    out.append(call_info)
            self._walk_for_calls(child, out, class_names, local_names)

    def _resolve_cpp_call(
        self, node: Node, class_names: set[str], local_names: set[str],
    ) -> CallInfo | None:
        func = node.child_by_field_name("function")
        if not func:
            return None

        line = node.start_point[0] + 1

        if func.type == "qualified_identifier":
            scope = func.child_by_field_name("scope")
            name_part = func.child_by_field_name("name")
            scope_str = self._node_text(scope) if scope else None
            callee = self._node_text(name_part) if name_part else self._node_text(func)

            if scope_str and "this" in scope_str:
                return CallInfo(
                    caller_name="", callee_name=callee, line=line,
                    resolution_method="same_scope", is_self_call=True, receiver="this",
                )
            if scope_str in class_names:
                return CallInfo(
                    caller_name="", callee_name=callee, line=line,
                    resolution_method="static_call", receiver=scope_str,
                )
            return CallInfo(
                caller_name="", callee_name=callee, line=line,
                resolution_method="dynamic_dispatch", receiver=scope_str,
            )

        if func.type in ("identifier", "field_identifier"):
            callee = self._node_text(func)
            if callee in class_names:
                return CallInfo(
                    caller_name="", callee_name=callee, line=line,
                    resolution_method="constructor",
                )
            if callee in local_names:
                return CallInfo(
                    caller_name="", callee_name=callee, line=line,
                    resolution_method="same_file",
                )
            return CallInfo(
                caller_name="", callee_name=callee, line=line,
                resolution_method="unresolved",
            )

        return None

    def _extract_type_usages(self, symbols: list[SymbolInfo]) -> list[TypeUsageInfo]:
        """Extract type references from parameters and return types."""
        usages: list[TypeUsageInfo] = []
        for sym in symbols:
            if sym.return_type:
                usages.append(TypeUsageInfo(
                    symbol_name=sym.name, type_name=sym.return_type,
                    usage_context="return_type", line=sym.line_start,
                ))
            for p in sym.parameters:
                if p.type:
                    usages.append(TypeUsageInfo(
                        symbol_name=sym.name, type_name=p.type,
                        usage_context="parameter", line=sym.line_start,
                    ))
            for child in sym.children:
                if child.return_type:
                    usages.append(TypeUsageInfo(
                        symbol_name=child.name, type_name=child.return_type,
                        usage_context="return_type", line=child.line_start,
                    ))
                for p in child.parameters:
                    if p.type:
                        usages.append(TypeUsageInfo(
                            symbol_name=child.name, type_name=p.type,
                            usage_context="parameter", line=child.line_start,
                        ))
        return usages
