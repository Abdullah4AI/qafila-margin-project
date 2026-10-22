with winning_quotes as (
    select *
    from {{ ref('stg_supplier_prices') }}
    where rejection_reason is null
    qualify row_number() over (
        partition by sku, valid_from order by source_file desc, source_row desc
    ) = 1
)
select q.source_file, q.source_row, q.sku, q.valid_from
from winning_quotes q
left join {{ ref('product_cost_history') }} h
    on q.sku = h.sku
    and q.valid_from >= h.valid_from
    and (q.valid_from < h.valid_to or h.valid_to is null)
    and q.unit_cost_sar = h.unit_cost_sar
group by q.source_file, q.source_row, q.sku, q.valid_from
having count(h.sku) != 1
