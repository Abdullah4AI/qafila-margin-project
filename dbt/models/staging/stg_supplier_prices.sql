with source_rows as (
    select
        source_file,
        source_row,
        trim(sku) as sku,
        cast(valid_from as date) as valid_from,
        coalesce(cost_sar, unit_cost) as raw_cost
    from {{ source('raw', 'supplier_prices') }}
), parsed as (
    select
        *,
        try_cast(
            replace(replace(
                translate(trim(raw_cost), '٠١٢٣٤٥٦٧٨٩', '0123456789'),
                '٫', '.'), ',', '.')
            as decimal(38, 18)
        ) as parsed_cost
    from source_rows
), classified as (
    select
        *,
        case
            when not exists (
                select 1 from {{ ref('stg_products') }} p where p.sku = parsed.sku
            ) then 'unknown_sku'
            when parsed_cost is null or parsed_cost <= 0 then 'invalid_cost'
        end as rejection_reason
    from parsed
)
select
    source_file,
    source_row,
    sku,
    valid_from,
    raw_cost,
    parsed_cost,
    cast(round(parsed_cost, 2) as double) as unit_cost_sar,
    rejection_reason
from classified
