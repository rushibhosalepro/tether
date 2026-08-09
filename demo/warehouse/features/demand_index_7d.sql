-- feature: demand_index_7d
-- rolling 7-day demand signal
select
    date_trunc('day', created_at) as day,
    sum(quantity) as demand_index_7d
from analytics.public.orders
where created_at >= dateadd(day, -7, current_date)
group by 1
