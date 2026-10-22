select
    source_file,
    source_row,
    sku,
    valid_from,
    raw_cost,
    rejection_reason as reason
from {{ ref('stg_supplier_prices') }}
where rejection_reason is not null
