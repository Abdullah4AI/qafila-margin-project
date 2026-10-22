select sku, valid_from, count(*) as versions
from {{ ref('product_cost_history') }}
group by sku, valid_from
having count(*) != 1
