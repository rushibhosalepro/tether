-- feature: margin_band
-- gross margin bucketed into bands, per product
select
    product_id,
    case
        when (list_price - unit_cost) / nullif(list_price, 0) > 0.5 then 'high'
        when (list_price - unit_cost) / nullif(list_price, 0) > 0.2 then 'mid'
        else 'low'
    end as margin_band
from analytics.public.products
