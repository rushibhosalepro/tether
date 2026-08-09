# Test log

One line per test, written when it happens. Pass or fail, failures stay in.
This is the evidence at submission time, built as we go, not assembled at the end.

---

## Unit tests (no DataHub needed) — 18/18 passing

These prove the logic. They do not touch the graph, so they are not the headline number.

**Classifier rules (9)**
- No ML model reads the column → PASS (does not block)
- Drop a column a live model reads → BLOCK
- Rename a column a live model reads → BLOCK
- Change a column's meaning silently → BLOCK
- Widen a type (int→bigint, float→double, date→timestamp) → WARN, not BLOCK
- Change type class (number→text) → BLOCK
- Model exists but nothing is deployed → WARN, not BLOCK

**LLM safety boundary (5)**
- The LLM cannot turn a PASS into a BLOCK
- The LLM can only downgrade a BLOCK to a WARN
- If the LLM errors, the block stays (fails safe)
- If the LLM returns junk, the block stays (fails safe)
- A block secretly tagged as LLM-made is rejected

**Diff parser (4)**
- Finds a dropped column in a dbt model change
- Finds exactly one change, no phantoms
- Reads DDL rename and type change
- Ignores non-SQL files

---

## DataHub integration (go/no-go) — PASSED 2026-08-09

Tested against live DataHub OSS (quickstart). This is the real proof.

- PASS — sqlglot recovers `orders.discount_pct`, `orders.total_amount` from real feature SQL (CASE + aggregation), not a flat SELECT
- PASS — emit a Snowflake dataset with columns via the SDK
- PASS — emit an mlFeature, mlModel and deployment via the SDK
- PASS — walk from a dataset to the models that consume it (dataset ← feature ← model)
- PASS — raise an incident on a model (returned an incident URN)
- PASS — write the inferred source edge back to a feature
- FAIL — `datahub datapack load` (both packs): SDK 1.7.0 loader bug, not our code path. Worked around: we emit our own graph, which is what the project does anyway.

### Three things the live test corrected about the plan

- An `mlFeature` will **not** accept an `upstreamLineage` aspect. Column-level lineage cannot live on a feature. The native edge is dataset-level (`MLFeatureProperties.sources`). Column precision becomes recorded *evidence*, which is fine, it is what Tether adds.
- The walk must use the **relationships API** (`DerivedFrom` incoming, then `Consumes` incoming), not `searchAcrossLineage` from the dataset, which returns nothing for datasets.
- The repairable "missing edge" is a feature with no `sources`. Repair = write `sources` back.

---

## The repair loop (the headline) — mechanism PROVEN, benchmark pending

- PASS — cold graph (feature has no source) → walk finds 0 models → the miss
- PASS — repair (write inferred `sources`) → walk finds the model → the catch
- [ ] Run over 8 real benchmark cases: expect ~3/8 cold → ~7/8 warm
- [ ] One case stays unfixable (Python transform, no SQL), refused both times
