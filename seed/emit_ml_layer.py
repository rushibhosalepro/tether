"""Emit the ML layer onto showcase-ecommerce.

The five sample datapacks ship no ML entities, which is exactly why the Production ML
Agents track is thin. This script closes that gap: feature tables, features, model groups,
models, deployments, and the edges that connect a Snowflake column to a model that is
currently serving.

Two lineage mechanisms are emitted deliberately:

  1. `MLFeatureProperties.sources` gives the dataset -> feature edge, which every DataHub
     version renders.
  2. `fineGrainedLineages` on the feature gives the column -> feature edge, which is what
     Tether actually wants. If a given DataHub build does not surface it in
     searchAcrossLineage, the walk falls back to the dataset edge plus the
     `source_columns` custom property, and says so in the output rather than pretending.

Run: `python -m seed.emit_ml_layer` or `tether seed`.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tether.config import settings  # noqa: E402
from tether.graph.resolve import resolve_dataset, schema_field_urn  # noqa: E402

SPEC = Path(__file__).with_name("entities.yaml")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ts_ms(date_str: str) -> int:
    from datetime import datetime, timezone

    return int(datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc).timestamp() * 1000)


def main(dry_run: bool = False) -> int:
    import datahub.emitter.mce_builder as builder
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.emitter.rest_emitter import DatahubRestEmitter
    from datahub.metadata.schema_classes import (
        FineGrainedLineageClass,
        FineGrainedLineageDownstreamTypeClass,
        FineGrainedLineageUpstreamTypeClass,
        MLFeaturePropertiesClass,
        MLFeatureTablePropertiesClass,
        MLModelDeploymentPropertiesClass,
        MLModelGroupPropertiesClass,
        MLModelPropertiesClass,
        OwnerClass,
        OwnershipClass,
        OwnershipTypeClass,
        UpstreamLineageClass,
    )

    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    env = spec.get("env", "PROD")
    platform = spec.get("platform", "mlflow")
    emitter = None if dry_run else DatahubRestEmitter(gms_server=settings.gms_url, token=settings.token or None)

    mcps: list[MetadataChangeProposalWrapper] = []
    unresolved: list[str] = []
    feature_urns: dict[str, str] = {}  # "table.feature" -> urn

    def emit(urn: str, aspect) -> None:
        mcps.append(MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect))

    def ownership(names: list[str]):
        return OwnershipClass(
            owners=[
                OwnerClass(owner=builder.make_user_urn(n), type=OwnershipTypeClass.TECHNICAL_OWNER)
                for n in names
            ]
        )

    # ---- feature tables and features -------------------------------------------------
    for ft in spec["feature_tables"]:
        ft_urn = builder.make_ml_feature_table_urn(ft.get("platform", "feast"), ft["name"])
        names: list[str] = []

        for f in ft["features"]:
            f_urn = builder.make_ml_feature_urn(ft["name"], f["name"])
            names.append(f_urn)
            feature_urns[f"{ft['name']}.{f['name']}"] = f_urn

            ds_urn = resolve_dataset(f["source_table"]) if not dry_run else None
            if not ds_urn and not dry_run:
                unresolved.append(f["source_table"])

            emit(
                f_urn,
                MLFeaturePropertiesClass(
                    description=f.get("description"),
                    dataType=f.get("type", "CONTINUOUS"),
                    sources=[ds_urn] if ds_urn else [],
                    customProperties={
                        "source_table": f["source_table"],
                        "source_columns": ",".join(f["source_columns"]),
                        "seeded_by": "tether",
                    },
                ),
            )

            # column -> feature, the edge the whole product depends on
            if ds_urn:
                emit(
                    f_urn,
                    UpstreamLineageClass(
                        upstreams=[],
                        fineGrainedLineages=[
                            FineGrainedLineageClass(
                                upstreamType=FineGrainedLineageUpstreamTypeClass.FIELD_SET,
                                downstreamType=FineGrainedLineageDownstreamTypeClass.FIELD,
                                upstreams=[schema_field_urn(ds_urn, c) for c in f["source_columns"]],
                                downstreams=[f_urn],
                                confidenceScore=1.0,
                            )
                        ],
                    ),
                )

        emit(
            ft_urn,
            MLFeatureTablePropertiesClass(
                description=ft.get("description"), mlFeatures=names, customProperties={"seeded_by": "tether"}
            ),
        )

    # ---- model groups -----------------------------------------------------------------
    group_urns: dict[str, str] = {}
    for g in spec.get("model_groups", []):
        g_urn = builder.make_ml_model_group_urn(platform, g["name"], env)
        group_urns[g["name"]] = g_urn
        emit(g_urn, MLModelGroupPropertiesClass(description=g.get("description")))

    # ---- models and deployments -------------------------------------------------------
    for m in spec["models"]:
        m_urn = builder.make_ml_model_urn(platform, m["name"], env)
        dep = m.get("deployment")
        dep_urns: list[str] = []

        if dep:
            d_urn = builder.make_ml_model_deployment_urn(platform, dep["name"], env)
            dep_urns.append(d_urn)
            emit(
                d_urn,
                MLModelDeploymentPropertiesClass(
                    description=f"Serving endpoint for {m['name']}",
                    createdAt=_ts_ms(m["last_trained"]),
                    status=dep["status"],
                    customProperties={"seeded_by": "tether"},
                ),
            )

        emit(
            m_urn,
            MLModelPropertiesClass(
                description=m.get("description"),
                date=_ts_ms(m["last_trained"]),
                version=None,
                mlFeatures=[feature_urns[f] for f in m["features"] if f in feature_urns],
                groups=[group_urns[m["group"]]] if m.get("group") in group_urns else [],
                deployments=dep_urns,
                trainingMetrics=[],
                hyperParams=[],
                customProperties={
                    "last_trained": m["last_trained"],
                    "seeded_by": "tether",
                    **{k: str(v) for k, v in (m.get("metrics") or {}).items()},
                },
            ),
        )
        if m.get("owners"):
            emit(m_urn, ownership(m["owners"]))

    # ---- ship it ----------------------------------------------------------------------
    print(f"{len(mcps)} aspects prepared for {settings.gms_url}")
    if unresolved:
        print("UNRESOLVED source tables (fix entities.yaml or load the datapack first):")
        for t in sorted(set(unresolved)):
            print(f"  - {t}")
    if dry_run:
        for mcp in mcps:
            print(f"  {mcp.aspectName:32} {mcp.entityUrn}")
        return 1 if unresolved else 0

    for mcp in mcps:
        emitter.emit(mcp)
    print(f"emitted {len(mcps)} aspects at {_now_ms()}")
    print(f"open {settings.frontend_url}/browse/mlModels to check")
    return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main(dry_run="--dry-run" in sys.argv))
