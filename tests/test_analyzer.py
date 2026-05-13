from __future__ import annotations

import asyncio
from pathlib import Path

from kb_agent.analyzer.pipeline import AnalysisPipeline
from kb_agent.models.entry import Layer


def run(coro):
    return asyncio.run(coro)


class TestPipelineStaticOnly:
    def test_pipeline_produces_entries(self, sample_repo: Path, tmp_path: Path):
        pipeline = AnalysisPipeline(
            repo_root=sample_repo, out_dir=tmp_path, llm_client=None
        )
        manifest = run(pipeline.run())

        assert manifest.stats.total_entries > 0
        assert "entries" in str(list(tmp_path.iterdir()))

    def test_pipeline_has_all_layers(self, sample_repo: Path, tmp_path: Path):
        pipeline = AnalysisPipeline(
            repo_root=sample_repo, out_dir=tmp_path, llm_client=None
        )
        manifest = run(pipeline.run())

        by_layer = manifest.stats.by_layer
        assert by_layer.get("arch", 0) >= 1
        assert by_layer.get("mod", 0) >= 1
        assert by_layer.get("mem", 0) >= 3  # At least 3 member entries

    def test_manifest_json_written(self, sample_repo: Path, tmp_path: Path):
        pipeline = AnalysisPipeline(
            repo_root=sample_repo, out_dir=tmp_path, llm_client=None
        )
        run(pipeline.run())

        manifest_path = tmp_path / "manifest.json"
        assert manifest_path.exists()

    def test_entry_files_written(self, sample_repo: Path, tmp_path: Path):
        pipeline = AnalysisPipeline(
            repo_root=sample_repo, out_dir=tmp_path, llm_client=None
        )
        run(pipeline.run())

        entries_dir = tmp_path / "entries"
        assert entries_dir.exists()
        json_files = list(entries_dir.glob("*.json"))
        assert len(json_files) >= 3

    def test_entry_ids_follow_convention(self, sample_repo: Path, tmp_path: Path):
        pipeline = AnalysisPipeline(
            repo_root=sample_repo, out_dir=tmp_path, llm_client=None
        )
        run(pipeline.run())

        entries_dir = tmp_path / "entries"
        filenames = [f.stem for f in entries_dir.glob("*.json")]

        arch_files = [f for f in filenames if f.startswith("arch_")]
        mod_files = [f for f in filenames if f.startswith("mod_")]
        mem_files = [f for f in filenames if f.startswith("mem_")]

        assert len(arch_files) >= 1
        assert len(mod_files) >= 1
        assert len(mem_files) >= 1

    def test_empty_repo(self, tmp_path: Path):
        empty = tmp_path / "empty_repo"
        empty.mkdir()
        out = tmp_path / "out"
        pipeline = AnalysisPipeline(repo_root=empty, out_dir=out, llm_client=None)
        manifest = run(pipeline.run())
        assert manifest.stats.total_entries == 0
