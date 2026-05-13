from __future__ import annotations

from kb_agent.models.entry import Language
from kb_agent.parser.base import BaseParser


def get_parser(language: Language) -> BaseParser:
    """Return the correct parser instance for the given language."""
    if language == Language.PYTHON:
        from kb_agent.parser.python_parser import PythonParser
        return PythonParser()
    elif language == Language.CSHARP:
        from kb_agent.parser.csharp_parser import CSharpParser
        return CSharpParser()
    elif language == Language.CPP:
        from kb_agent.parser.cpp_parser import CppParser
        return CppParser()
    raise ValueError(f"No parser for language: {language}")
