with intervals as (
    select
        *,
        lead(valid_from) over (partition by sku order by valid_from) as next_start,
        lag(unit_cost_sar) over (partition by sku order by valid_from) as previous_cost
    from {{ ref('product_cost_history') }}
)
select *
from intervals
where valid_to is distinct from next_start
    or is_current is distinct from (valid_to is null)
    or valid_to <= valid_from
    or unit_cost_sar = previous_cost
    or unit_cost_sar < 0
    or unit_cost_sar != round(unit_cost_sar, 2)
