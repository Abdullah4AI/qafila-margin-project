select
    order_id,
    line_no,
    product_id,
    quantity,
    -- Keep money decimal until the published contract calls for doubles.
    cast(unit_price as decimal(24, 8)) as unit_price,
    cast(discount as decimal(24, 8)) as discount
from {{ source('raw', 'order_items') }}
