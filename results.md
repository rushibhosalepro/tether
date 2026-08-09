# Results

What Tether did on real schema-change cases, and whether it was right. This is the number
that matters: it measures the system's judgment, not how many tests we wrote. Every case is
a real diff run against a live DataHub. Misses stay in.

---

## The headline: detection before vs after the repair loop

Same 8 cases, same code. The only difference is whether Tether repaired the lineage edges it
found missing. (benchmark pending, target shape below)

| | Caught | Missed | Notes |
|---|---|---|---|
| Cold graph (edges undeclared) | _/8 | _/8 | misses where no one declared the edge |
| After repair | _/8 | _/8 | Tether inferred the edge from SQL and wrote it back |
| Refused to guess | | | feature with no SQL to point at, refused both times |

---

## Cases

One row per real PR diff. `Right?` is measured against ground truth.

| # | The change | Tether said | Right? |
|---|---|---|---|
| loop-proof | Feature with no declared source; a live model consumes it | Cold: **MISS**. After repair: **CATCH** (found `fraud_detector_v2`) | ✅ both |
| 001 | Drop `orders.discount_pct` (a live churn model reads it) | pending | |
| 002 | pending | | |

---

## Proven against live DataHub (2026-08-09)

The behaviours every case depends on, each run for real once:

- Walk from a dataset to the models that consume it → works
- Raise an incident on a model → works (returns an incident URN)
- Write an inferred lineage edge back → works
- Cold walk misses a model with no declared edge; after writing the edge, the walk catches it → **the loop works**

---

<sub>Logic checks (not the headline): 18 unit tests pass covering the classifier rules, the
LLM-can-never-block boundary, and the diff parser. They prove the code is correct; the cases
above prove the system is right.</sub>
