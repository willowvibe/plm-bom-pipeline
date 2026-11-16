-- Enriched multi-level BOM explosion as of as_of_date.
--
-- One row per product traversal path (the same grain as int_bom_explosion),
-- with the product, family and child part attributes analysts need for cost
-- and weight analysis. extended_cost prices the accumulated quantity of the
-- child part; is_leaf flags parts that are not assemblies.

select
    e.product_id,
    p.name as product_name,
    p.family_id,
    f.family_name,
    e.root_part_id,
    e.level,
    e.path,
    e.parent_part_id,
    e.child_part_id,
    child.name as part_name,
    child.part_type,
    child.uom,
    child.standard_cost,
    child.weight_kg,
    e.quantity,
    e.accumulated_quantity,
    cast(
        e.accumulated_quantity * child.standard_cost as decimal(18, 4)
    ) as extended_cost,
    child.part_type <> 'assembly' as is_leaf
from {{ ref('int_bom_explosion') }} as e
inner join {{ ref('stg_products') }} as p
    on p.product_id = e.product_id
inner join {{ ref('stg_families') }} as f
    on f.family_id = p.family_id
inner join {{ ref('stg_parts') }} as child
    on child.part_id = e.child_part_id
