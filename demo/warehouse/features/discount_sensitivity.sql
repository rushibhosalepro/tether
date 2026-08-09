-- feature: discount_sensitivity
-- ratio of discounted spend to total spend, per customer, last 90 days
select
    customer_id,
    sum(case when discount_pct > 0 then total_amount else 0 end)
        / nullif(sum(total_amount), 0) as discount_sensitivity
from analytics.public.orders
where created_at >= dateadd(day, -90, current_date)
group by customer_id
