{{ config(materialized='table') }}

select
    product_id,
    sku,
    category,
    unit_cost,
    list_price
from {{ source('raw', 'products') }}
