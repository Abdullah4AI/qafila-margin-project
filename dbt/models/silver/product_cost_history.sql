with winners as (
    -- A rejected quote cannot overwrite a usable quote, including in a fix file.
    select sku, valid_from, unit_cost_sar
    from {{ ref('stg_supplier_prices') }}
    where rejection_reason is null
    qualify row_number() over (
        partition by sku, valid_from
        order by source_file desc, source_row desc
    ) = 1
), observations as (
    select
        *,
        lag(unit_cost_sar) over (partition by sku order by valid_from) as previous_cost
    from winners
), changes as (
    -- Missing weeks produce no observation, so the last cost stays in force.
    select sku, unit_cost_sar, valid_from
    from observations
    where previous_cost is null or unit_cost_sar != previous_cost
), intervals as (
    select
        *,
        lead(valid_from) over (partition by sku order by valid_from) as valid_to
    from changes
)
select sku, unit_cost_sar, valid_from, valid_to, valid_to is null as is_current
from intervals
