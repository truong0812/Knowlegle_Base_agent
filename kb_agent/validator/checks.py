from __future__ import annotations

from kb_agent.models.entry import KBEntry, Layer
from kb_agent.models.report import CheckResult


def check_parent_consistency(
    entries: list[KBEntry],
    entry_map: dict[str, KBEntry] | None = None,
) -> CheckResult:
    """Every entry.parent must exist. Layer ordering must be arch > mod > mem."""
    if entry_map is None:
        entry_map = {e.id: e for e in entries}
    ids = set(entry_map.keys())
    layer_order = {Layer.ARCH: 0, Layer.MOD: 1, Layer.MEM: 2}
    affected: list[str] = []

    for entry in entries:
        if entry.parent and entry.parent not in ids:
            affected.append(entry.id)
        if entry.parent:
            parent = entry_map.get(entry.parent)
            if parent and layer_order.get(entry.layer, 99) <= layer_order.get(parent.layer, 99):
                affected.append(entry.id)

    return CheckResult(
        name="parent_consistency",
        passed=len(affected) == 0,
        details=f"{len(affected)} entries with inconsistent parent" if affected else "All parents consistent",
        affected_entries=affected,
    )


def check_orphan_entries(entries: list[KBEntry]) -> CheckResult:
    """Arch entries should have children. Mod entries should have children."""
    affected: list[str] = []
    for entry in entries:
        if entry.layer in (Layer.ARCH, Layer.MOD) and not entry.children:
            affected.append(entry.id)

    return CheckResult(
        name="orphan_detection",
        passed=len(affected) == 0,
        details=f"{len(affected)} parent entries with no children" if affected else "No orphans",
        affected_entries=affected,
    )


def check_low_confidence(entries: list[KBEntry], threshold: float = 0.7) -> list[str]:
    """Return IDs of entries with confidence below threshold."""
    return [e.id for e in entries if e.ai.confidence > 0 and e.ai.confidence < threshold]
