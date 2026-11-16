-- Product-level BOM roll-up as of as_of_date.
--
-- One row per product. Cost and weight are summed over leaf parts only
-- (part_type <> 'assembly') so that assembly values, which are already built
-- from their children, are not counted twice. Every product appears even when
-- its explosion is empty, with zeros.

with exploded as (

    select
        product_id,
        level,
        part_type,
        accumulated_quantity,
        standard_cost,
        weight_kg
    from {{ ref('bom_explosion') }}

),

rollup as (

    select
        product_id,
        sum(
            case
                when part_type <> 'assembly'
                    then accumulated_quantity * standard_cost
                else 0
            end
        ) as total_cost,
        sum(
            case
                when part_type <> 'assembly'
                    then accumulated_quantity * weight_kg
                else 0
            end
        ) as total_weight_kg,
        sum(case when level > 0 then 1 else 0 end) as bom_line_count,
        max(level) as max_depth
    from exploded
    group by product_id

)

select
    p.product_id,
    p.name as product_name,
    p.family_id,
    f.family_name,
    cast(coalesce(r.total_cost, 0) as decimal(18, 4)) as total_cost,
    cast(coalesce(r.total_weight_kg, 0) as decimal(18, 4)) as total_weight_kg,
    cast(coalesce(r.bom_line_count, 0) as integer) as bom_line_count,
    cast(coalesce(r.max_depth, 0) as integer) as max_depth
from {{ ref('stg_products') }} as p
inner join {{ ref('stg_families') }} as f
    on f.family_id = p.family_id
left join rollup as r
    on r.product_id = p.product_id
