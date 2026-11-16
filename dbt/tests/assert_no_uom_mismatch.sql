-- Fails when a BOM line's unit of measure differs from the child part's
-- base unit of measure.

select
    b.bom_line_id,
    b.parent_part_id,
    b.child_part_id,
    b.uom as bom_uom,
    p.uom as part_uom
from {{ ref('stg_boms') }} as b
inner join {{ ref('stg_parts') }} as p
    on p.part_id = b.child_part_id
where b.uom <> p.uom
