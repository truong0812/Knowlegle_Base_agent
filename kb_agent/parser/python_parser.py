from __future__ import annotations

import ast
from typing import Sequence

import tree_sitter_python as tspython
from tree_sitter import Language as TSLanguage, Parser, Node

from kb_agent.models.entry import Language, Parameter, SymbolKind
from kb_agent.parser.base import AssignmentInfo, BaseParser, CallInfo, ImportInfo, ParseResult, SymbolInfo, TypeUsageInfo, normalize_decorator


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
        calls = self._extract_calls(tree.root_node, symbols)
        type_usages = self._extract_type_usages(tree.root_node, symbols)
        assignments = self._extract_assignments(tree.root_node)
        return ParseResult(
            file_path=file_path,
            language=Language.PYTHON,
            symbols=symbols,
            imports=imports,
            calls=calls,
            type_usages=type_usages,
            assignments=assignments,
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
                decorators = self._extract_decorator_names(child)
                target = child.children[-1]
                if target.type == "class_definition":
                    sym = self._extract_class(target)
                    sym.modifiers.extend(decorators)
                    out.append(sym)
                elif target.type == "function_definition":
                    sym = self._extract_function(target)
                    sym.modifiers.extend(decorators)
                    out.append(sym)
            # Recurse into module/block only (not class bodies — methods handled by _extract_class)
            if depth < 2 and child.type in ("module", "block"):
                self._walk_for_symbols(child, out, depth + 1)

    def _extract_class(self, node: Node) -> SymbolInfo:
        name = self._get_child_by_type(node, "identifier")
        name_str = self._node_text(name) if name else "<unknown>"

        # Extract base classes from argument_list
        bases: list[str] = []
        for child in node.children:
            if child.type == "argument_list":
                for arg in child.children:
                    if arg.type in ("identifier", "attribute", "dotted_name"):
                        bases.append(self._node_text(arg))

        # Extract methods from class body
        children: list[SymbolInfo] = []
        body = self._get_child_by_type(node, "block")
        if body:
            for child in body.children:
                if child.type == "function_definition":
                    children.append(self._extract_function(child))
                elif child.type == "decorated_definition":
                    decorators = self._extract_decorator_names(child)
                    target = child.children[-1]
                    if target.type == "function_definition":
                        fn = self._extract_function(target)
                        fn.modifiers.extend(decorators)
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
            bases=bases,
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
        ast_imports = self._extract_imports_with_ast(self._node_text(root_node))
        if ast_imports:
            return ast_imports

        imports: list[ImportInfo] = []
        self._walk_for_imports(root_node, imports)
        return imports

    def _extract_imports_with_ast(self, source: str) -> list[ImportInfo]:
        """Extract Python imports with alias information using the stdlib AST."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        return self._imports_from_ast(tree)

    def _imports_from_ast(self, tree: ast.AST) -> list[ImportInfo]:
        """Convert AST import nodes into ImportInfo records."""
        imports: list[ImportInfo] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_name = alias.name.split(".")[0]
                    aliases = (
                        {alias.asname: imported_name}
                        if alias.asname else {}
                    )
                    imports.append(ImportInfo(
                        module_path=alias.name,
                        imported_names=[imported_name],
                        aliases=aliases,
                    ))
            elif isinstance(node, ast.ImportFrom):
                imports.append(ImportInfo(
                    module_path=node.module or "",
                    imported_names=[alias.name for alias in node.names],
                    aliases={
                        alias.asname: alias.name
                        for alias in node.names
                        if alias.asname
                    },
                ))
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
        imports = self._imports_from_ast(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                children = []
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        children.append(self._ast_func_to_symbol(item))
                docstring = ast.get_docstring(node)
                bases = [ast.unparse(b) for b in node.bases]
                symbols.append(
                    SymbolInfo(
                        name=node.name,
                        kind=SymbolKind.CLASS,
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        signature=f"class {node.name}",
                        docstring=docstring,
                        children=children,
                        bases=bases,
                    )
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Only top-level functions (not inside class — handled above)
                if not isinstance(getattr(node, "_parent", None), ast.ClassDef):
                    symbols.append(self._ast_func_to_symbol(node))
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

    def _extract_decorator_names(self, decorated_node: Node) -> list[str]:
        """Extract specific decorator names from a decorated_definition node."""
        names: list[str] = []
        for child in decorated_node.children:
            if child.type == "decorator":
                text = self._node_text(child).lstrip("@")
                name = normalize_decorator(text.split("(")[0].strip())
                if name:
                    names.append(name)
        return names

    def _extract_calls(self, root_node: Node, symbols: list[SymbolInfo]) -> list[CallInfo]:
        """Walk AST for call nodes, resolve to CallInfo with resolution method."""
        class_names = {s.name for s in symbols if s.kind == SymbolKind.CLASS}
        local_func_names = {s.name for s in symbols if s.kind == SymbolKind.FUNCTION}
        # Map class name to its method decorator info
        class_method_decorators: dict[str, dict[str, list[str]]] = {}
        for cls in symbols:
            if cls.kind == SymbolKind.CLASS:
                for m in cls.children:
                    local_func_names.add(m.name)
                    if m.modifiers:
                        class_method_decorators.setdefault(cls.name, {})[m.name] = m.modifiers

        calls: list[CallInfo] = []
        self._walk_for_calls(root_node, calls, class_names, local_func_names, class_method_decorators)
        return calls

    def _walk_for_calls(
        self,
        node: Node,
        out: list[CallInfo],
        class_names: set[str],
        local_names: set[str],
        class_method_decorators: dict[str, dict[str, list[str]]],
        enclosing_class: str | None = None,
    ) -> None:
        for child in node.children:
            if child.type == "call":
                call_info = self._resolve_call(
                    child, class_names, local_names, class_method_decorators, enclosing_class,
                )
                if call_info:
                    out.append(call_info)
            elif child.type == "class_definition":
                name_node = self._get_child_by_type(child, "identifier")
                new_enclosing = self._node_text(name_node) if name_node else enclosing_class
                self._walk_for_calls(
                    child, out, class_names, local_names,
                    class_method_decorators, new_enclosing,
                )
                continue
            if child.type not in ("import_statement", "import_from_statement"):
                self._walk_for_calls(
                    child, out, class_names, local_names,
                    class_method_decorators, enclosing_class,
                )

    def _resolve_call(
        self,
        call_node: Node,
        class_names: set[str],
        local_names: set[str],
        class_method_decorators: dict[str, dict[str, list[str]]],
        enclosing_class: str | None = None,
    ) -> CallInfo | None:
        func_node = call_node.child_by_field_name("function")
        if not func_node:
            return None

        line = call_node.start_point[0] + 1

        if func_node.type == "attribute":
            obj = func_node.child_by_field_name("object")
            attr = func_node.child_by_field_name("attribute")
            receiver = self._node_text(obj) if obj else None
            callee = self._node_text(attr) if attr else "<unknown>"

            if receiver == "self":
                return CallInfo(
                    caller_name="", callee_name=callee, line=line,
                    resolution_method="same_scope", is_self_call=True, receiver="self",
                    enclosing_class=enclosing_class,
                )
            if receiver in class_names:
                method_mods = class_method_decorators.get(receiver, {}).get(callee, [])
                if "staticmethod" in method_mods or "classmethod" in method_mods:
                    return CallInfo(
                        caller_name="", callee_name=callee, line=line,
                        resolution_method="static_call", receiver=receiver,
                        enclosing_class=enclosing_class,
                    )
                return CallInfo(
                    caller_name="", callee_name=callee, line=line,
                    resolution_method="static_call", receiver=receiver,
                    enclosing_class=enclosing_class,
                )
            return CallInfo(
                caller_name="", callee_name=callee, line=line,
                resolution_method="dynamic_dispatch", receiver=receiver,
                enclosing_class=enclosing_class,
            )

        if func_node.type == "identifier":
            callee = self._node_text(func_node)
            if callee in class_names:
                return CallInfo(
                    caller_name="", callee_name=callee, line=line,
                    resolution_method="constructor",
                    enclosing_class=enclosing_class,
                )
            if callee in local_names:
                return CallInfo(
                    caller_name="", callee_name=callee, line=line,
                    resolution_method="same_file",
                    enclosing_class=enclosing_class,
                )
            return CallInfo(
                caller_name="", callee_name=callee, line=line,
                resolution_method="unresolved",
                enclosing_class=enclosing_class,
            )

        return None

    def _extract_assignments(self, root_node: Node) -> list[AssignmentInfo]:
        """Extract variable assignments where RHS is a simple function call.

        Captures patterns like: svc = get_service()
        Does NOT capture: svc = obj.method(), svc = a + b, etc.
        """
        assignments: list[AssignmentInfo] = []
        self._walk_for_assignments(root_node, assignments)
        return assignments

    def _walk_for_assignments(self, node: Node, out: list[AssignmentInfo]) -> None:
        for child in node.children:
            if child.type == "assignment":
                lhs = child.child_by_field_name("left")
                rhs = child.child_by_field_name("right")
                if lhs and lhs.type == "identifier" and rhs and rhs.type == "call":
                    func_node = rhs.child_by_field_name("function")
                    if func_node and func_node.type == "identifier":
                        out.append(AssignmentInfo(
                            variable_name=self._node_text(lhs),
                            callee_name=self._node_text(func_node),
                            line=child.start_point[0] + 1,
                        ))
            if child.type not in ("import_statement", "import_from_statement"):
                self._walk_for_assignments(child, out)

    def _extract_type_usages(
        self, root_node: Node, symbols: list[SymbolInfo],
    ) -> list[TypeUsageInfo]:
        """Extract type references from parameters, return types, annotations."""
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
