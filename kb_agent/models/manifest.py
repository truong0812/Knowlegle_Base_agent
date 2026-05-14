from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KBStats(BaseModel):
    total_entries: int = 0
    by_layer: dict[str, int] = Field(
        default_factory=lambda: {"arch": 0, "mod": 0, "file": 0, "mem": 0}
    )
    coverage: float = 0.0
    avg_confidence: float = 0.0


class Manifest(BaseModel):
    version: str = "1.0"
    source_repo: str = ""
    source_commit: str | None = None
    languages: list[str] = Field(default_factory=list)
    stats: KBStats = Field(default_factory=KBStats)
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
