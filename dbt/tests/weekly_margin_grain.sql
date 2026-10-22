select iso_week, city, category, count(*) as rows_per_group
from {{ ref('weekly_margin') }}
group by iso_week, city, category
having count(*) != 1
