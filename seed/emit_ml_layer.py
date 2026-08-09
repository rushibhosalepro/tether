"""Emit the ML layer onto our own Snowflake-shaped datasets.

showcase-ecommerce ships no ML entities, which is why the Production ML Agents track is thin.
This emits the missing layer from seed/entities.yaml: datasets, feature tables, features,
model groups, models, deployments, and the lineage edges.

Lineage is dataset-level (verified against OSS: an mlFeature rejects upstreamLineage). The
edge is MLFeatureProperties.sources, which DataHub stores as a DerivedFrom relationship.
Models link to features via MLModelProperties.mlFeatures (a Consumes relationship).

--partial omits every edge marked `declared: false` in entities.yaml. That is the realistic
day-one graph: models whose inputs nobody declared. Tether's repair step puts them back.

Run: `python -m seed.emit_ml_layer [--partial] [--dry-run]`
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tether.config import settings  # noqa: E402

SPEC = Path(__file__).with_name("entities.yaml")


def _ts_ms(date_str: str) -> int:
    from datetime import datetime, timezone

    return int(datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc).timestamp() * 1000)


def main(dry_run: bool = False, partial: bool = False) -> int:
    import datahub.emitter.mce_builder as b
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.emitter.rest_emitter import DatahubRestEmitter
    from datahub.metadata.schema_classes import (
        DatasetPropertiesClass,
        MLFeaturePropertiesClass,
        MLFeatureTablePropertiesClass,
        MLModelDeploymentPropertiesClass,
        MLModelGroupPropertiesClass,
        MLModelPropertiesClass,
        DeploymentStatusClass,
        NumberTypeClass,
        OtherSchemaClass,
        OwnerClass,
        OwnershipClass,
        OwnershipTypeClass,
        SchemaFieldClass,
        SchemaFieldDataTypeClass,
        SchemaMetadataClass,
    )

    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    env = spec.get("env", "PROD")
    platform = spec.get("platform", "mlflow")
    emitter = None if dry_run else DatahubRestEmitter(gms_server=settings.gms_url, token=settings.token or None)

    mcps: list[MetadataChangeProposalWrapper] = []
    omitted: list[str] = []

    def emit(urn: str, aspect) -> None:
        mcps.append(MetadataChangeProposalWrapper(entityUrn=urn, aspect=aspect))

    def ds_urn(name: str, plat: str) -> str:
        return b.make_dataset_urn(plat, name, env)

    # ---- datasets with columns -------------------------------------------------------
    ds_lookup: dict[str, str] = {}
    for ds in spec["datasets"]:
        urn = ds_urn(ds["name"], ds["platform"])
        ds_lookup[ds["name"]] = urn
        emit(urn, DatasetPropertiesClass(name=ds["name"].split(".")[-1]))
        emit(
            urn,
            SchemaMetadataClass(
                schemaName=ds["name"].split(".")[-1],
                platform=b.make_data_platform_urn(ds["platform"]),
                version=0,
                hash="",
                platformSchema=OtherSchemaClass(rawSchema=""),
                fields=[
                    SchemaFieldClass(
                        fieldPath=c,
                        type=SchemaFieldDataTypeClass(type=NumberTypeClass()),
                        nativeDataType="NUMBER",
                    )
                    for c in ds["columns"]
                ],
            ),
        )

    # ---- feature tables --------------------------------------------------------------
    ft_features: dict[str, list[str]] = {ft["name"]: [] for ft in spec["feature_tables"]}
    feature_urn: dict[str, str] = {}

    # ---- features (with or without the source edge) ----------------------------------
    for f in spec["features"]:
        f_urn = b.make_ml_feature_urn(f["table"], f["name"])
        feature_urn[f["name"]] = f_urn
        ft_features[f["table"]].append(f_urn)

        # full mode emits every edge; partial mode omits the undeclared ones
        declared = f.get("declared", True)
        omit = partial and not declared
        sources = [] if omit else [ds_lookup[f["source_dataset"]]]
        if omit:
            omitted.append(f"{f['name']} <- {f['source_dataset']}")

        emit(
            f_urn,
            MLFeaturePropertiesClass(
                description=f"feature computed by {f['computed_by']}",
                dataType="CONTINUOUS",
                sources=sources,
            ),
        )

    for ft in spec["feature_tables"]:
        emit(
            b.make_ml_feature_table_urn(ft["platform"], ft["name"]),
            MLFeatureTablePropertiesClass(description=ft.get("description"), mlFeatures=ft_features[ft["name"]]),
        )

    # ---- model groups ----------------------------------------------------------------
    group_urn: dict[str, str] = {}
    for g in spec.get("model_groups", []):
        gu = b.make_ml_model_group_urn(platform, g["name"], env)
        group_urn[g["name"]] = gu
        emit(gu, MLModelGroupPropertiesClass(description=g.get("description")))

    # ---- models + deployments --------------------------------------------------------
    for m in spec["models"]:
        m_urn = b.make_ml_model_urn(platform, m["name"], env)
        dep = m.get("deployment")
        dep_urns: list[str] = []
        if dep:
            d_urn = b.make_ml_model_deployment_urn(platform, dep["name"], env)
            dep_urns.append(d_urn)
            emit(
                d_urn,
                MLModelDeploymentPropertiesClass(
                    description=f"Serving endpoint for {m['name']}",
                    createdAt=_ts_ms(m["last_trained"]),
                    status=DeploymentStatusClass.IN_SERVICE,
                ),
            )
        emit(
            m_urn,
            MLModelPropertiesClass(
                description=m.get("description"),
                date=_ts_ms(m["last_trained"]),
                mlFeatures=[feature_urn[f] for f in m["features"] if f in feature_urn],
                groups=[group_urn[m["group"]]] if m.get("group") in group_urn else [],
                deployments=dep_urns,
                customProperties={
                    "last_trained": m["last_trained"],
                    "seeded_by": "tether",
                    # deployment entities are not queryable over OSS GraphQL, so the serving
                    # signal lives here where the walk can read it.
                    "serving": "true" if dep else "false",
                },
            ),
        )
        if m.get("owners"):
            emit(
                m_urn,
                OwnershipClass(
                    owners=[
                        OwnerClass(owner=b.make_user_urn(o), type=OwnershipTypeClass.TECHNICAL_OWNER)
                        for o in m["owners"]
                    ]
                ),
            )

    # ---- ship it ---------------------------------------------------------------------
    mode = "PARTIAL" if partial else "FULL"
    print(f"[{mode}] {len(mcps)} aspects prepared for {settings.gms_url}")
    if omitted:
        print(f"omitted {len(omitted)} undeclared edge(s) (Tether should repair these):")
        for o in omitted:
            print(f"  - {o}")
    if dry_run:
        return 0

    for mcp in mcps:
        emitter.emit(mcp)
    print(f"emitted {len(mcps)} aspects")
    print(f"open {settings.frontend_url}/browse/mlModels to check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(dry_run="--dry-run" in sys.argv, partial="--partial" in sys.argv))
