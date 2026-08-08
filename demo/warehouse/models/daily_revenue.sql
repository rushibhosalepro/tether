{{ config(materialized='table') }}

-- A dashboard reads this. Impact analysis that stops at the BI layer stops here.
select
    date_trunc('day', created_at) as day,
    sum(total_amount) as revenue,
    count(*) as order_count
from {{ ref('orders') }}
group by 1
