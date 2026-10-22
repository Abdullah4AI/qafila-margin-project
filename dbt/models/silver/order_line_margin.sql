{{ config(materialized='view') }}

select
    i.order_id,
    i.line_no,
    o.order_date,
    cast(week(o.order_date) as integer) as iso_week,
    s.city,
    p.category,
    p.sku,
    i.quantity,
    cast(round(i.quantity * i.unit_price - i.discount, 2) as decimal(28, 2)) as revenue_sar,
    h.valid_from as cost_valid_from,
    h.valid_to as cost_valid_to,
    h.unit_cost_sar,
    h.sku is not null as is_costed,
    i.quantity * cast(h.unit_cost_sar as decimal(28, 2)) as cost_sar
from {{ ref('stg_order_items') }} i
inner join {{ ref('stg_orders') }} o on i.order_id = o.order_id
inner join {{ ref('stg_products') }} p on i.product_id = p.product_id
inner join {{ ref('stg_stores') }} s on o.store_id = s.store_id
left join {{ ref('product_cost_history') }} h
    on p.sku = h.sku
    and o.order_date >= h.valid_from
    and (o.order_date < h.valid_to or h.valid_to is null)
where o.status = 'delivered'
    and i.quantity > 0
    and o.order_date >= date '2026-08-31'
