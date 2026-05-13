from __future__ import annotations

import tree_sitter_c_sharp as tscs
from tree_sitter import Language as TSLanguage, Parser, Node

from kb_agent.models.entry import Language, Parameter, SymbolKind
from kb_agent.parser.base import BaseParser, ImportInfo, ParseResult, SymbolInfo


class CSharpParser(BaseParser):
    def __init__(self) -> None:
        self._language = TSLanguage(tscs.language())
        self._parser = Parser(self._language)

    def parse_file(self, source: bytes, file_path: str) -> ParseResult:
        errors: list[str] = []
        tree = self._parser.parse(source)

        symbols = self.extract_symbols(tree.root_node)
        imports = self.extract_imports(tree.root_node)
        return ParseResult(
            file_path=file_path,
            language=Language.CSHARP,
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
