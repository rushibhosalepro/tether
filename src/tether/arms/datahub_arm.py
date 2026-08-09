"""Treatment arm: full DataHub lineage, dataset -> feature -> model -> deployment."""

from __future__ import annotations

from ..graph.walk import ml_impacts as _walk
from ..verdict.models import Impact


def ml_impacts(dataset_urn: str, column: str | None = None, **_: object) -> list[Impact]:
    return _walk(dataset_urn, column)
