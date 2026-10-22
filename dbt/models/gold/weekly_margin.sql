with totals as (
    select
        iso_week,
        city,
        category,
        cast(count(*) as integer) as lines,
        sum(revenue_sar) as revenue_sar,
        sum(case when is_costed then revenue_sar else 0 end) as costed_revenue_sar,
        sum(coalesce(cost_sar, 0)) as cost_sar,
        cast(count(*) filter (where not is_costed) as integer) as uncosted_lines
    from {{ ref('order_line_margin') }}
    group by iso_week, city, category
)
select
    iso_week,
    city,
    category,
    lines,
    cast(round(revenue_sar, 2) as double) as revenue_sar,
    cast(round(costed_revenue_sar, 2) as double) as costed_revenue_sar,
    cast(round(cost_sar, 2) as double) as cost_sar,
    cast(round(costed_revenue_sar - cost_sar, 2) as double) as margin_sar,
    uncosted_lines
from totals
