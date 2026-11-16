-- Fails when a part has no incoming BOM line and is not a product's
-- top-level part. Such parts cannot be reached from any product.

select
    p.part_id,
    p.part_number,
    p.name,
    p.part_type
from {{ ref('stg_parts') }} as p
where not exists (
    select 1
    from {{ ref('stg_boms') }} as b
    where b.child_part_id = p.part_id
)
and not exists (
    select 1
    from {{ ref('stg_products') }} as pr
    where pr.top_level_part_id = p.part_id
)
