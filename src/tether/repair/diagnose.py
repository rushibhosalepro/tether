"""Turn a cold miss into a diagnosed lineage gap. Deterministic, no LLM.

When the walk from a changed column reaches no model, there are two possibilities:
  1. genuinely nothing consumes it  -> not a gap, leave it
  2. a feature's SQL *does* read it, but the dataset->feature edge was never declared, so the
     walk could not see it  -> a gap Tether can repair

This module distinguishes them by reading the feature SQL (repair.infer) and cross-checking
against the features DataHub already links to the dataset. It only reports a gap it can prove.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import settings
from ..graph.resolve import resolve_dataset
from ..graph.walk import features_of
from . import infer


@dataclass
class LineageGap:
    column: str                 # the changed column, e.g. "orders.discount_pct"
    dataset_urn: str
    feature: str                # the feature whose SQL reads the column
    feature_urn: str
    evidence: str               # file:line proving it
    provable: bool              # False when the feature has no SQL (Python) -> a refusal


def _all_feature_names() -> list[str]:
    """Every feature Tether knows how to reason about = every SQL/py file it can see."""
    d = settings.features_dir
    if not d.exists():
        return []
    return sorted(p.stem for p in d.iterdir() if p.suffix in (".sql", ".py"))


def diagnose(table: str, column: str) -> list[LineageGap]:
    """Find features that read this column but are not linked to its dataset in the graph."""
    dataset_urn = resolve_dataset(table)
    if not dataset_urn:
        return []

    linked = {f.get("name") for f in features_of(dataset_urn)}
    gaps: list[LineageGap] = []

    for feature in _all_feature_names():
        if feature in linked:
            continue  # edge already declared, no gap
        ev = infer.infer(feature)
        reads_column = ev.provable and column.lower() in ev.columns
        looks_unprovable = (not ev.provable) and _py_reads(feature, column)
        if not (reads_column or looks_unprovable):
            continue
        gaps.append(
            LineageGap(
                column=f"{table}.{column}",
                dataset_urn=dataset_urn,
                feature=feature,
                feature_urn=_feature_urn(feature),
                evidence=ev.cite() if ev.provable else f"{feature}.py (no SQL)",
                provable=ev.provable,
            )
        )
    return gaps


def _py_reads(feature: str, column: str) -> bool:
    """Weak signal that a Python feature references the column, so we can flag a refusal."""
    p = settings.features_dir / f"{feature}.py"
    if not p.exists():
        return False
    return column.lower() in p.read_text(encoding="utf-8").lower()


def _feature_urn(feature: str) -> str:
    """Reconstruct the feature URN. Table name is recorded in entities.yaml; default here."""
    import datahub.emitter.mce_builder as b
    import yaml
    from pathlib import Path

    spec = yaml.safe_load((Path(settings.features_dir).parents[2] / "seed" / "entities.yaml").read_text("utf-8"))
    table = next((f["table"] for f in spec["features"] if f["name"] == feature), "customer_churn_features")
    return b.make_ml_feature_urn(table, feature)
