-- feature: avg_basket_value
select
    customer_id,
    avg(total_amount) as avg_basket_value
from analytics.public.orders
group by customer_id
