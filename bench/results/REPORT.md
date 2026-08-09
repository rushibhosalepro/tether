# Benchmark: detection before vs after the repair loop

Same cases, same code, live graph. The only difference between the two columns is whether
Tether repaired the lineage edges it found missing.

**Breakages caught: cold 3/6 -> warm 5/6.** Repaired 2 edges, refused 1.

| Column | Expected | Cold | After repair |
|---|---|---|---|
| `orders.discount_pct` | BLOCK | PASS ❌ | BLOCK ✅ |
| `orders.quantity` | BLOCK | PASS ❌ | BLOCK ✅ |
| `orders.total_amount` | BLOCK | BLOCK ✅ | BLOCK ✅ |
| `orders.order_id` | BLOCK | BLOCK ✅ | BLOCK ✅ |
| `products.unit_cost` | BLOCK | BLOCK ✅ | BLOCK ✅ |
| `customers.support_tickets` (Python, refused) | BLOCK | PASS ❌ | PASS ❌ |
| `orders.status` | PASS | PASS ✅ | PASS ✅ |

## Edges repaired

- discount_sensitivity <- analytics.public.orders (features\discount_sensitivity.sql:5)
- demand_index_7d <- analytics.public.orders (features\demand_index_7d.sql:5)

## Refused (no SQL to prove the edge)

- support_sentiment: no SQL expression to prove the analytics.public.customers.support_tickets dependency