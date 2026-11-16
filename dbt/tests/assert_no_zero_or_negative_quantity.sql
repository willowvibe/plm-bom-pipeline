-- Fails when a BOM line has a quantity of zero or less.

select
    bom_line_id,
    parent_part_id,
    child_part_id,
    quantity,
    uom
from {{ ref('stg_boms') }}
where quantity <= 0
