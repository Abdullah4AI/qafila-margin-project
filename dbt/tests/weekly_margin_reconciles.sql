with line_totals as (
    select
        iso_week,
        city,
        category,
        count(*) as lines,
        sum(revenue_sar) as revenue_sar,
        sum(case when is_costed then revenue_sar else 0 end) as costed_revenue_sar,
        sum(coalesce(cost_sar, 0)) as cost_sar,
        count(*) filter (where not is_costed) as uncosted_lines
    from {{ ref('order_line_margin') }}
    group by iso_week, city, category
)
select m.*, t.lines as expected_lines
from {{ ref('weekly_margin') }} m
full outer join line_totals t using (iso_week, city, category)
where m.lines is null or t.lines is null
    or m.lines != t.lines
    or m.lines <= 0
    or m.uncosted_lines != t.uncosted_lines
    or m.uncosted_lines < 0 or m.uncosted_lines > m.lines
    or abs(m.revenue_sar - t.revenue_sar) > 0.001
    or abs(m.costed_revenue_sar - t.costed_revenue_sar) > 0.001
    or abs(m.cost_sar - t.cost_sar) > 0.001
    or abs(m.margin_sar - (t.costed_revenue_sar - t.cost_sar)) > 0.001
