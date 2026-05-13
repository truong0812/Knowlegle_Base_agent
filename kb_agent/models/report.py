from __future__ import annotations

from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    name: str
    passed: bool
    details: str | None = None
    affected_entries: list[str] = Field(default_factory=list)


class QualityReport(BaseModel):
    coverage: float = 0.0
    consistency: float = 0.0
    avg_confidence: float = 0.0
    total_entries: int = 0
    checks: list[CheckResult] = Field(default_factory=list)
    low_confidence_entries: list[str] = Field(default_factory=list)
