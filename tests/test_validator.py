from __future__ import annotations

import asyncio
from pathlib import Path

from kb_agent.analyzer.pipeline import AnalysisPipeline
from kb_agent.models.report import QualityReport
from kb_agent.validator.validator import KBValidator


def run(coro):
    return asyncio.run(coro)


class TestValidator:
    def test_validate_produces_report(self, sample_repo: Path, tmp_path: Path):
        pipeline = AnalysisPipeline(
            repo_root=sample_repo, out_dir=tmp_path, llm_client=None
        )
        run(pipeline.run())

        validator = KBValidator(tmp_path)
        report = validator.validate()

        assert isinstance(report, QualityReport)
        assert report.total_entries > 0

    def test_quality_report_file_written(self, sample_repo: Path, tmp_path: Path):
        pipeline = AnalysisPipeline(
            repo_root=sample_repo, out_dir=tmp_path, llm_client=None
        )
        run(pipeline.run())

        validator = KBValidator(tmp_path)
        validator.validate()

        assert (tmp_path / "quality_report.json").exists()

    def test_parent_consistency_passes(self, sample_repo: Path, tmp_path: Path):
        pipeline = AnalysisPipeline(
            repo_root=sample_repo, out_dir=tmp_path, llm_client=None
        )
        run(pipeline.run())

        validator = KBValidator(tmp_path)
        report = validator.validate()

        parent_check = next(c for c in report.checks if c.name == "parent_consistency")
        assert parent_check.passed

    def test_empty_kb(self, tmp_path: Path):
        validator = KBValidator(tmp_path)
        report = validator.validate()
        assert report.total_entries == 0
