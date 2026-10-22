with expected as (
    select source_file, source_row, sku, valid_from, raw_cost, rejection_reason as reason
    from {{ ref('stg_supplier_prices') }}
    where rejection_reason is not null
), actual as (
    select source_file, source_row, sku, valid_from, raw_cost, reason
    from {{ ref('price_quarantine') }}
)
(select * from expected except all select * from actual)
union all
(select * from actual except all select * from expected)
