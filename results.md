# Results

What Tether did on real schema-change cases, and whether it was right. This is the number
that matters: it measures the system's judgment, not how many tests we wrote. Every case is
a real diff run against a live DataHub. Misses stay in.

---

## The headline: detection before vs after the repair loop

Same cases, same code, run against the live graph. The only difference is whether Tether
repaired the lineage edges it found missing. Verified 2026-08-09.

| | Breakages caught | Missed | Notes |
|---|---|---|---|
| Cold graph (edges undeclared) | 3 / 6 | 3 | misses where no one declared the edge |
| After repair | **5 / 6** | 1 | Tether inferred 2 edges from SQL and wrote them back |
| Refused to guess | | 1 | `support_sentiment` is computed in Python; no SQL to point at, refused |

The repair is real: delete it and the warm run equals the cold run. The 2 edges Tether wrote
back (`discount_sensitivity`, `demand_index_7d`) each carry the SQL `file:line` as evidence
and a `tether:inferred` tag, so nobody mistakes them for declared truth.

---

## Cases

One row per real column change, run against the live partial graph. "Cold" = the day-one
graph where some edges were never declared. "After repair" fills in once the repair module
lands. Ground truth is in `seed/ground_truth.yaml`.

| The change | Reads (from SQL) | Live model | Cold | Should be |
|---|---|---|---|---|
| drop `orders.discount_pct` | discount_sensitivity | churn_propensity_v4 | **MISS** (edge undeclared) | BLOCK |
| drop `orders.quantity` | demand_index_7d | dynamic_pricing_v2 | **MISS** (edge undeclared) | BLOCK |
| drop `orders.total_amount` | avg_basket_value | churn_propensity_v4 | **CATCH** | BLOCK |
| drop `orders.order_id` | order_frequency_90d | churn_propensity_v4 | **CATCH** | BLOCK |
| drop `products.unit_cost` | margin_band | dynamic_pricing_v2 | **CATCH** | BLOCK |
| drop `orders.status` | (nothing) | none | **PASS** ✅ | PASS |
| drop `customers.support_tickets` | support_sentiment (Python) | churn_propensity_v4 | **MISS** | BLOCK, but unprovable |

Cold catches 3 of 6 real breakages, correctly passes the true-negative, and misses 3. After
repair, `discount_pct` and `quantity` flip to CATCH; `support_tickets` stays a miss because
Tether refuses to infer the Python feature's edge.

Column precision is real: dropping `orders.status` correctly touches nothing, because no
feature's SQL reads it. The walk is not just "any column in a consumed table".

## The repair loop, proven end-to-end (live DataHub)

- COLD: `discount_pct` MISS, `quantity` MISS, `support_tickets` MISS
- DIAGNOSE: found the feature whose SQL reads each column but whose edge was undeclared
- REPAIR: wrote `discount_sensitivity <- orders` (evidence `discount_sensitivity.sql:5`) and
  `demand_index_7d <- orders` (evidence `demand_index_7d.sql:5`); **refused** `support_sentiment`
  (Python, no SQL)
- WARM: `discount_pct` -> churn_propensity_v4, `quantity` -> dynamic_pricing_v2,
  `support_tickets` -> still MISS

---

## Real PRs on a separate public repo

Tether runs against a separate, public "data team" repo so the checks are on someone else's
PRs, not our own: **https://github.com/rushibhosalepro/tether-demo-warehouse/pulls**

Four real PRs, each dropping one column, each judged against the live DataHub graph:

| PR | Change | Tether status | Right? |
|---|---|---|---|
| #1 | drop `orders.discount_pct` | 🔴 failure, blocks `churn_propensity_v4` (@aman) | ✅ |
| #2 | drop `orders.quantity` | 🔴 failure, blocks `dynamic_pricing_v2` (@wenjia) | ✅ |
| #3 | drop `products.unit_cost` | 🔴 failure, blocks `dynamic_pricing_v2` | ✅ |
| #4 | drop `orders.status` | 🟢 success, no ML impact | ✅ |

Each blocked PR carries a red `tether` commit status (greys out merge), a comment naming the
model and owner, and a real incident filed on the model in DataHub. Verified on GitHub 2026-08-09.

Note: check runs need a GitHub App, so the last-mile verb is a commit status, which works with
a normal token and gates merge the same way.

## A real change, run end-to-end with write-backs (live DataHub)

`tether check` on the `drop orders.discount_pct` diff (warm graph), write-backs ON:

- Verdict: **BLOCK**, rule R1, `churn_propensity_v4` (live), owner @aman
- Raised a real incident on the model: `urn:li:incident:...` (priority CRITICAL)
- Wrote an institutional-memory link recording the dependency and the PR
- Re-running reuses the same incident (idempotent), it does not spam the model page

## Proven against live DataHub (2026-08-09)

The behaviours every case depends on, each run for real:

- Walk from a dataset to the models that consume it → works
- Raise an incident on a model → works (returns an incident URN)
- Write an inferred lineage edge back → works
- Write an institutional-memory link → works (on the dataset; OSS rejects a column URN)
- Cold walk misses a model with no declared edge; after writing the edge, the walk catches it → **the loop works**

---

<sub>Logic checks (not the headline): 34 unit tests pass covering the classifier rules, the
LLM-can-never-block boundary, the repair-never-guesses boundary, the diff parser (multi-column,
adds, retypes), report roll-up, and SQL inference across every feature. They prove the code is
correct; the PRs above prove the system is right.</sub>
