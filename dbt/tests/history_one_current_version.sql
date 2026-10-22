select sku, count(*) filter (where is_current) as current_versions
from {{ ref('product_cost_history') }}
group by sku
having count(*) filter (where is_current) != 1
