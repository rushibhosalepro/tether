"""The shared vocabulary. Every other module speaks in these types."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class ChangeKind(str, Enum):
    DROP = "DROP"
    RENAME = "RENAME"
    RETYPE = "RETYPE"
    SEMANTIC = "SEMANTIC"  # same name and type, different meaning (units, enum values)


class Level(str, Enum):
    BLOCK = "BLOCK"
    WARN = "WARN"
    PASS = "PASS"


class DecidedBy(str, Enum):
    """Who produced the level. The LLM may only ever appear as SOFTENED."""

    DETERMINISTIC = "deterministic"
    LLM_SOFTENED = "llm_softened"


@dataclass
class ColumnChange:
    """One column-level change extracted from an unmerged diff."""

    table: str  # e.g. "analytics.public.orders" as written in the SQL
    column: str
    kind: ChangeKind
    old_type: str | None = None
    new_type: str | None = None
    new_name: str | None = None  # only for RENAME
    source_file: str = ""
    source_line: int = 0

    def label(self) -> str:
        return f"{self.table}.{self.column}"


@dataclass
class Impact:
    """One production ML consumer reached by walking forward from a changed column."""

    model_urn: str
    model_name: str
    feature_urn: str | None = None
    feature_name: str | None = None
    deployment_urn: str | None = None
    deployment_status: str | None = None  # e.g. "IN_SERVICE"
    owners: list[str] = field(default_factory=list)
    last_trained: str | None = None  # ISO8601
    hops: list[str] = field(default_factory=list)  # the URN path, column -> ... -> model

    @property
    def is_live(self) -> bool:
        return self.deployment_status == "IN_SERVICE"


@dataclass
class Verdict:
    change: ColumnChange
    level: Level
    impacts: list[Impact] = field(default_factory=list)
    reason: str = ""
    rule_id: str = ""  # which rule in verdict/rules.md fired
    decided_by: DecidedBy = DecidedBy.DETERMINISTIC
    llm_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["change"]["kind"] = self.change.kind.value
        d["level"] = self.level.value
        d["decided_by"] = self.decided_by.value
        return d


@dataclass
class Report:
    """The whole run: every change, its verdict, and the roll-up."""

    pr_url: str
    verdicts: list[Verdict] = field(default_factory=list)

    @property
    def level(self) -> Level:
        if any(v.level is Level.BLOCK for v in self.verdicts):
            return Level.BLOCK
        if any(v.level is Level.WARN for v in self.verdicts):
            return Level.WARN
        return Level.PASS

    @property
    def blocked_models(self) -> list[Impact]:
        seen: dict[str, Impact] = {}
        for v in self.verdicts:
            if v.level is Level.BLOCK:
                for i in v.impacts:
                    seen[i.model_urn] = i
        return list(seen.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "pr_url": self.pr_url,
            "level": self.level.value,
            "verdicts": [v.to_dict() for v in self.verdicts],
        }
