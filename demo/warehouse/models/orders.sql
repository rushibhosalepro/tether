{{ config(materialized='table') }}

-- The fact table every downstream thing hangs off. Changing a column here is the
-- single most common way to silently break something two hops away.
select
    order_id,
    customer_id,
    created_at,
    quantity,
    unit_price,
    discount_pct,
    total_amount,
    status
from {{ source('raw', 'orders') }}
