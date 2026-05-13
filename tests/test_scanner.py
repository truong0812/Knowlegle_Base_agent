from __future__ import annotations

from pathlib import Path

from kb_agent.models.entry import Language
from kb_agent.scanner.ignore import KbignoreMatcher
from kb_agent.scanner.language import detect_language
from kb_agent.scanner.scanner import FileScanner


class TestDetectLanguage:
    def test_python(self):
        assert detect_language(Path("foo.py")) == Language.PYTHON

    def test_csharp(self):
        assert detect_language(Path("Foo.cs")) == Language.CSHARP

    def test_cpp(self):
        assert detect_language(Path("foo.cpp")) == Language.CPP
        assert detect_language(Path("foo.hpp")) == Language.CPP
        assert detect_language(Path("foo.h")) == Language.CPP

    def test_unsupported(self):
        assert detect_language(Path("foo.rb")) is None
        assert detect_language(Path("foo.txt")) is None

    def test_case_insensitive(self):
        assert detect_language(Path("FOO.PY")) == Language.PYTHON


class TestKbignoreMatcher:
    def test_no_kbignore(self, tmp_path: Path):
        matcher = KbignoreMatcher(tmp_path)
        assert matcher.should_ignore("src/main.py") is False

    def test_pattern_match(self, tmp_path: Path):
        (tmp_path / ".kbignore").write_text("*.log\nvendor/\n")
        matcher = KbignoreMatcher(tmp_path)
        assert matcher.should_ignore("debug.log") is True
        assert matcher.should_ignore("vendor/foo.py") is True
        assert matcher.should_ignore("src/main.py") is False

    def test_comment_and_blank_lines(self, tmp_path: Path):
        (tmp_path / ".kbignore").write_text("# comment\n\n*.db\n")
        matcher = KbignoreMatcher(tmp_path)
        assert matcher.should_ignore("data.db") is True
        assert matcher.should_ignore("main.py") is False


class TestFileScanner:
    def test_scan_sample_repo(self, sample_repo: Path):
        scanner = FileScanner(sample_repo)
        entries = scanner.scan()

        langs = {e.language for e in entries}
        assert Language.PYTHON in langs
        assert Language.CSHARP in langs
        assert Language.CPP in langs
        assert len(entries) == 3

    def test_skip_unsupported(self, tmp_path: Path):
        (tmp_path / "readme.md").write_text("hello")
        (tmp_path / "app.py").write_text("print('hi')")
        scanner = FileScanner(tmp_path)
        entries = scanner.scan()
        assert len(entries) == 1
        assert entries[0].language == Language.PYTHON

    def test_skip_hidden_dirs(self, tmp_path: Path):
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        (hidden / "secret.py").write_text("x = 1")
        (tmp_path / "main.py").write_text("print('hi')")
        scanner = FileScanner(tmp_path)
        entries = scanner.scan()
        assert len(entries) == 1
        assert entries[0].path == "main.py"

    def test_build_directory_tree(self, sample_repo: Path):
        scanner = FileScanner(sample_repo)
        tree = scanner.build_directory_tree()
        assert "src" in tree
