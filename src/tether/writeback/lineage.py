"""Write an inferred lineage edge back to DataHub. The only load-bearing write-back.

The incident and the memory link tell a human something. This changes the graph itself: it
adds the dataset->feature edge (MLFeatureProperties.sources) that nobody declared, so the
next walk, the next engineer and the next agent all inherit it. That is the challenge text
verbatim: "writes results back so the next person or agent inherits the knowledge."

Two things keep it honest:
  * it is written with a `tether:inferred` tag, so no one mistakes it for a declared fact
  * it is only ever called with evidence (a SQL file and line). See repair/emit.py, which
    refuses to call this without provable columns.
"""

from __future__ import annotations

from ..config import settings

INFERRED_TAG = "urn:li:tag:tether:inferred"


def _sdk_emitter():
    from datahub.emitter.rest_emitter import DatahubRestEmitter

    return DatahubRestEmitter(gms_server=settings.gms_url, token=settings.token or None)


def write_source_edge(feature_urn: str, dataset_urn: str, evidence: str) -> None:
    """Add dataset_urn to the feature's sources, and record the evidence + inferred tag.

    Idempotent: re-running unions the dataset into whatever sources already exist.
    """
    import datahub.emitter.mce_builder as b
    from datahub.emitter.mcp import MetadataChangeProposalWrapper
    from datahub.metadata.schema_classes import (
        GlobalTagsClass,
        InstitutionalMemoryClass,
        InstitutionalMemoryMetadataClass,
        MLFeaturePropertiesClass,
        TagAssociationClass,
        AuditStampClass,
    )

    emitter = _sdk_emitter()
    existing = _current_sources(feature_urn)
    sources = sorted(set(existing) | {dataset_urn})

    emitter.emit(
        MetadataChangeProposalWrapper(
            entityUrn=feature_urn,
            aspect=MLFeaturePropertiesClass(
                description=f"source inferred by Tether from {evidence}",
                dataType="CONTINUOUS",
                sources=sources,
            ),
        )
    )
    emitter.emit(
        MetadataChangeProposalWrapper(
            entityUrn=feature_urn,
            aspect=GlobalTagsClass(tags=[TagAssociationClass(tag=INFERRED_TAG)]),
        )
    )
    stamp = AuditStampClass(time=0, actor="urn:li:corpuser:tether")
    emitter.emit(
        MetadataChangeProposalWrapper(
            entityUrn=feature_urn,
            aspect=InstitutionalMemoryClass(
                elements=[
                    InstitutionalMemoryMetadataClass(
                        url=f"https://github.com/tether#{evidence}",
                        description=f"Tether inferred this source from {evidence}",
                        createStamp=stamp,
                    )
                ]
            ),
        )
    )


def _current_sources(feature_urn: str) -> list[str]:
    from ..datahub_client import client

    q = """query($u:String!){ mlFeature(urn:$u){ properties{ sources{ urn } } } }"""
    try:
        d = client().graphql(q, {"u": feature_urn})
        return [s["urn"] for s in (((d or {}).get("mlFeature") or {}).get("properties") or {}).get("sources") or []]
    except Exception:
        return []
