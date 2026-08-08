{{ config(materialized='table') }}

select
    customer_id,
    signup_date,
    country,
    lifetime_value,
    segment
from {{ source('raw', 'customers') }}
