# Repair log (from `tether bench`, live DataHub)

Cold graph misses 3 of 6 breakages. Two of those are lineage edges nobody declared but that
Tether can prove from the feature SQL. It writes them back, tagged `tether:inferred`, with the
SQL `file:line` as evidence. The third has no SQL, so Tether refuses it.

## Repaired (proven from SQL)

- `discount_sensitivity <- analytics.public.orders`  evidence: `features/discount_sensitivity.sql:5`
- `demand_index_7d <- analytics.public.orders`  evidence: `features/demand_index_7d.sql:5`

## Refused (no SQL to point at)

- `support_sentiment` reads `customers.support_tickets`, but it is computed in a Python
  transform. Tether will not write an edge it cannot prove, so this stays a miss and is
  reported as one.

After repair, the two repaired columns flip from PASS (miss) to BLOCK (catch). The refused one
stays a miss. That is the honest 3/6 -> 5/6.
