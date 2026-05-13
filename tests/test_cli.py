"""Tests for CLI commands — scan, parse, analyze, validate, index, query."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from scripts.cli import app

runner = CliRunner()


@pytest.fixture
def sample_repo(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def hello(): pass\n")
    return tmp_path


class TestCLIScan:
    def test_scan_command(self, sample_repo: Path):
        result = runner.invoke(app, ["scan", "--repo", str(sample_repo)])
        assert result.exit_code == 0
        assert "Found" in result.stdout


class TestCLIParse:
    def test_parse_command(self, sample_repo: Path):
        result = runner.invoke(app, ["parse", "--repo", str(sample_repo)])
        assert result.exit_code == 0


class TestCLIAnalyze:
    def test_analyze_skip_ai(self, sample_repo: Path, tmp_path: Path):
        out = tmp_path / "kb_out"
        result = runner.invoke(app, [
            "analyze", "--repo", str(sample_repo), "--out", str(out), "--skip-ai"
        ])
        assert result.exit_code == 0
        assert (out / "manifest.json").exists()
        assert (out / "entries").exists()


class TestCLIValidate:
    def test_validate_no_kb(self, tmp_path: Path):
        result = runner.invoke(app, ["validate", "--kb", str(tmp_path / "no_kb")])
        assert result.exit_code == 0


class TestCLIIndex:
    def test_index_no_entries(self, tmp_path: Path):
        result = runner.invoke(app, ["index", "--kb", str(tmp_path / "empty")])
        assert result.exit_code == 1
        assert "No entries found" in result.stdout


class TestCLIQuery:
    def test_query_no_index(self, tmp_path: Path):
        result = runner.invoke(app, ["query", "test", "--kb", str(tmp_path)])
        assert result.exit_code == 1
