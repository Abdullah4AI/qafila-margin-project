-- Compare the reporting input back to the source, so a join cannot silently
-- lose an order line or multiply it when a cost interval overlaps another.
with expected as (
    select i.order_id, i.line_no
    from {{ source('raw', 'order_items') }} i
    inner join {{ source('raw', 'orders') }} o on i.order_id = o.order_id
    where o.status = 'delivered'
        and i.quantity > 0
        and cast(cast(o.created_at as timestamp) + interval '3 hours' as date) >= date '2026-08-31'
), actual as (
    select order_id, line_no from {{ ref('order_line_margin') }}
)
(select * from expected except all select * from actual)
union all
(select * from actual except all select * from expected)
