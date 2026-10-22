select
    order_id,
    store_id,
    status,
    -- The source is UTC. Riyadh is UTC+3 throughout the source period.
    cast(cast(created_at as timestamp) + interval '3 hours' as date) as order_date
from {{ source('raw', 'orders') }}
