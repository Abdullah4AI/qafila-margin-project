select *
from {{ ref('order_line_margin') }}
where is_costed != (unit_cost_sar is not null)
    or (not is_costed and cost_sar is not null)
    or (is_costed and (
        order_date < cost_valid_from
        or order_date >= cost_valid_to
        or cost_sar is null
        or abs(cost_sar - quantity * unit_cost_sar) > 0.000001
    ))
