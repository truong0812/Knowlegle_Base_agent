from __future__ import annotations

import json
from pathlib import Path

from kb_agent.models.entry import KBEntry
from kb_agent.models.report import CheckResult, QualityReport
from kb_agent.validator.checks import check_low_confidence, check_orphan_entries, check_parent_consistency


class KBValidator:
    """Load entries from .kb/ and run quality checks."""

    def __init__(self, kb_dir: Path) -> None:
        self._kb_dir = kb_dir.resolve()

    def validate(self) -> QualityReport:
        entries = self._load_entries()
        if not entries:
            return QualityReport()

        entry_map = {e.id: e for e in entries}
        checks: list[CheckResult] = [
            check_parent_consistency(entries, entry_map),
            check_orphan_entries(entries),
        ]

        confidences = [e.ai.confidence for e in entries if e.ai.confidence > 0]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

        low_conf = check_low_confidence(entries)

        report = QualityReport(
            coverage=1.0,
            consistency=sum(1 for c in checks if c.passed) / len(checks) if checks else 1.0,
            avg_confidence=avg_conf,
            total_entries=len(entries),
            checks=checks,
            low_confidence_entries=low_conf,
        )

        # Write report
        report_path = self._kb_dir / "quality_report.json"
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        return report

    def _load_entries(self) -> list[KBEntry]:
        entries_dir = self._kb_dir / "entries"
        if not entries_dir.exists():
            return []

        entries: list[KBEntry] = []
        for json_file in entries_dir.glob("*.json"):
            data = json.loads(json_file.read_text(encoding="utf-8"))
            entries.append(KBEntry(**data))
        return entries
