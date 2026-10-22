select order_id, line_no, count(*) as rows_per_line
from {{ ref('order_line_margin') }}
group by order_id, line_no
having count(*) != 1
