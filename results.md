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

Cold catches 3 of 6 real breakages, correctly passes the true-negative, and misses 3. Two of
those misses are repairable from SQL; one (the Python feature) Tether must refuse to guess.

Column precision is real: dropping `orders.status` correctly touches nothing, because no
feature's SQL reads it. The walk is not just "any column in a consumed table".

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
