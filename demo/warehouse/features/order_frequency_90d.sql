-- feature: order_frequency_90d
select
    customer_id,
    count(order_id) / 90.0 as order_frequency_90d
from analytics.public.orders
where created_at >= dateadd(day, -90, current_date)
group by customer_id
