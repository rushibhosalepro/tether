"""Treatment arm: full DataHub lineage, column -> feature -> model -> deployment."""

from __future__ import annotations

from ..graph.walk import ml_impacts as _walk
from ..verdict.models import Impact


def ml_impacts(column_urn: str, **_: object) -> list[Impact]:
    return _walk(column_urn)
