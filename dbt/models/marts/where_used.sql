-- Where-used analysis as of as_of_date.
--
-- One row per (child part, immediate parent part, product) with the direct
-- parent relationship preserved from int_where_used, enriched with readable
-- part and product names.

select
    wu.where_used_key,
    wu.child_part_id,
    child.name as child_part_name,
    child.part_type as child_part_type,
    wu.parent_part_id,
    parent.name as parent_part_name,
    parent.part_type as parent_part_type,
    wu.product_id,
    p.name as product_name,
    p.family_id
from {{ ref('int_where_used') }} as wu
inner join {{ ref('stg_parts') }} as child
    on child.part_id = wu.child_part_id
inner join {{ ref('stg_parts') }} as parent
    on parent.part_id = wu.parent_part_id
inner join {{ ref('stg_products') }} as p
    on p.product_id = wu.product_id
