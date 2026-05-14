from __future__ import annotations

import tree_sitter_c_sharp as tscs
from tree_sitter import Language as TSLanguage, Parser, Node

from kb_agent.models.entry import Language, Parameter, SymbolKind
from kb_agent.parser.base import BaseParser, CallInfo, ImportInfo, ParseResult, SymbolInfo, TypeUsageInfo


class CSharpParser(BaseParser):
    def __init__(self) -> None:
        self._language = TSLanguage(tscs.language())
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
            language=Language.CSHARP,
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
            if child.type == "namespace_declaration":
                self._walk(child, out, depth)
            elif child.type == "class_declaration":
                out.append(self._extract_class(child))
            elif child.type == "struct_declaration":
                out.append(self._extract_class(child, kind=SymbolKind.STRUCT))
            elif child.type == "interface_declaration":
                out.append(self._extract_class(child, kind=SymbolKind.INTERFACE))
            elif child.type == "enum_declaration":
                out.append(self._extract_enum(child))
            elif depth < 3:
                self._walk(child, out, depth + 1)

    def _extract_class(self, node: Node, kind: SymbolKind = SymbolKind.CLASS) -> SymbolInfo:
        name = node.child_by_field_name("name")
        name_str = self._node_text(name) if name else "<unknown>"

        modifiers = self._extract_modifiers(node)

        # Extract base classes/interfaces from base_list
        bases: list[str] = []
        for child in node.children:
            if child.type == "base_list":
                for bc in child.children:
                    if bc.type in ("identifier", "qualified_name", "type_name", "generic_name"):
                        bases.append(self._node_text(bc))

        children: list[SymbolInfo] = []
        body = self._get_body(node)
        if body:
            for child in body.children:
                if child.type == "method_declaration":
                    children.append(self._extract_method(child))
                elif child.type == "constructor_declaration":
                    children.append(self._extract_method(child, is_ctor=True))
                elif child.type == "property_declaration":
                    children.append(self._extract_property(child))

        keyword = "struct" if kind == SymbolKind.STRUCT else "interface" if kind == SymbolKind.INTERFACE else "class"
        sig = f"{' '.join(modifiers)} {keyword} {name_str}".strip()

        return SymbolInfo(
            name=name_str,
            kind=kind,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=sig,
            modifiers=modifiers,
            children=children,
            bases=bases,
        )

    def _extract_method(self, node: Node, is_ctor: bool = False) -> SymbolInfo:
        name = node.child_by_field_name("name")
        name_str = self._node_text(name) if name else "<unknown>"
        if is_ctor:
            # Constructor name comes from the return type field in tree-sitter C#
            ret = node.child_by_field_name("type")
            name_str = self._node_text(ret) if ret else name_str

        params = self._extract_parameters(node)
        ret_type = node.child_by_field_name("type")
        ret_str = self._node_text(ret_type) if ret_type and not is_ctor else None

        modifiers = self._extract_modifiers(node)

        sig = f"{' '.join(modifiers)} {name_str}({', '.join(self._format_param(p) for p in params)})"
        sig = sig.strip()

        return SymbolInfo(
            name=name_str,
            kind=SymbolKind.METHOD,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=sig,
            modifiers=modifiers,
            parameters=params,
            return_type=ret_str,
        )

    def _extract_property(self, node: Node) -> SymbolInfo:
        name = node.child_by_field_name("name")
        name_str = self._node_text(name) if name else "<unknown>"
        ret_type = node.child_by_field_name("type")
        ret_str = self._node_text(ret_type) if ret_type else None
        modifiers = self._extract_modifiers(node)

        return SymbolInfo(
            name=name_str,
            kind=SymbolKind.PROPERTY,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=f"{' '.join(modifiers)} {ret_str or '?'} {name_str}".strip(),
            modifiers=modifiers,
            return_type=ret_str,
        )

    def _extract_enum(self, node: Node) -> SymbolInfo:
        name = node.child_by_field_name("name")
        name_str = self._node_text(name) if name else "<unknown>"
        return SymbolInfo(
            name=name_str,
            kind=SymbolKind.ENUM,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            signature=f"enum {name_str}",
        )

    def _extract_parameters(self, node: Node) -> list[Parameter]:
        params_node = node.child_by_field_name("parameters")
        if not params_node:
            return []
        result: list[Parameter] = []
        for child in params_node.children:
            if child.type == "parameter":
                p_name = child.child_by_field_name("name")
                p_type = child.child_by_field_name("type")
                result.append(
                    Parameter(
                        name=self._node_text(p_name) if p_name else "?",
                        type=self._node_text(p_type) if p_type else None,
                    )
                )
        return result

    def _extract_modifiers(self, node: Node) -> list[str]:
        mods: list[str] = []
        for child in node.children:
            if child.type == "modifier":
                mods.append(self._node_text(child))
            elif child.type in ("public", "private", "protected", "internal", "static",
                                "abstract", "virtual", "override", "sealed", "readonly",
                                "async"):
                mods.append(child.type)
        return mods

    def extract_imports(self, root_node: Node) -> list[ImportInfo]:
        imports: list[ImportInfo] = []
        for child in root_node.children:
            if child.type == "using_directive":
                # 'name' field may not exist; grab identifier or qualified_name child
                name = child.child_by_field_name("name")
                if not name:
                    for c in child.children:
                        if c.type in ("identifier", "qualified_name", "namespace_name"):
                            name = c
                            break
                if name:
                    imports.append(ImportInfo(module_path=self._node_text(name)))
        return imports

    def _get_body(self, node: Node) -> Node | None:
        for child in node.children:
            if child.type == "declaration_list":
                return child
        return None

    @staticmethod
    def _format_param(p: Parameter) -> str:
        if p.type:
            return f"{p.type} {p.name}"
        return p.name

    def _extract_calls(self, root_node: Node, symbols: list[SymbolInfo]) -> list[CallInfo]:
        """Walk AST for invocation and object creation expressions."""
        class_names = {s.name for s in symbols if s.kind in (SymbolKind.CLASS, SymbolKind.STRUCT)}
        local_method_names: set[str] = set()
        for cls in symbols:
            if cls.kind in (SymbolKind.CLASS, SymbolKind.STRUCT):
                for m in cls.children:
                    local_method_names.add(m.name)

        calls: list[CallInfo] = []
        self._walk_for_calls(root_node, calls, class_names, local_method_names)
        return calls

    def _walk_for_calls(
        self, node: Node, out: list[CallInfo],
        class_names: set[str], local_names: set[str],
    ) -> None:
        for child in node.children:
            if child.type == "invocation_expression":
                call_info = self._resolve_csharp_call(child, class_names, local_names)
                if call_info:
                    out.append(call_info)
            elif child.type == "object_creation_expression":
                call_info = self._resolve_csharp_constructor(child, class_names)
                if call_info:
                    out.append(call_info)
            self._walk_for_calls(child, out, class_names, local_names)

    def _resolve_csharp_call(
        self, node: Node, class_names: set[str], local_names: set[str],
    ) -> CallInfo | None:
        func = node.child_by_field_name("function")
        if not func:
            return None

        line = node.start_point[0] + 1

        if func.type == "member_access_expression":
            expr = func.child_by_field_name("expression")
            name = func.child_by_field_name("name")
            receiver = self._node_text(expr) if expr else None
            callee = self._node_text(name) if name else "<unknown>"

            if receiver == "this":
                return CallInfo(
                    caller_name="", callee_name=callee, line=line,
                    resolution_method="same_scope", is_self_call=True, receiver="this",
                )
            if receiver in class_names:
                return CallInfo(
                    caller_name="", callee_name=callee, line=line,
                    resolution_method="static_call", receiver=receiver,
                )
            return CallInfo(
                caller_name="", callee_name=callee, line=line,
                resolution_method="dynamic_dispatch", receiver=receiver,
            )

        if func.type == "identifier":
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

    def _resolve_csharp_constructor(
        self, node: Node, class_names: set[str],
    ) -> CallInfo | None:
        type_node = node.child_by_field_name("type")
        if not type_node:
            return None
        callee = self._node_text(type_node)
        line = node.start_point[0] + 1
        if callee in class_names:
            return CallInfo(
                caller_name="", callee_name=callee, line=line,
                resolution_method="constructor",
            )
        return CallInfo(
            caller_name="", callee_name=callee, line=line,
            resolution_method="unresolved",
        )

    def _extract_type_usages(self, symbols: list[SymbolInfo]) -> list[TypeUsageInfo]:
        """Extract type references from parameters, return types, properties."""
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
