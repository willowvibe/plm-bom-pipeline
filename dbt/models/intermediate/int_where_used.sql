-- Direct where-used relationships: each row says that product_id uses
-- child_part_id through the immediate parent_part_id. Because a product can
-- reach the same part through more than one path, distinct removes duplicates
-- from the row-per-path explosion.

with explosion as (

    select
        product_id,
        parent_part_id,
        child_part_id
    from {{ ref('int_bom_explosion') }}
    where level > 0

)

select distinct
    child_part_id,
    parent_part_id,
    product_id,
    child_part_id || '|' || parent_part_id || '|' || product_id as where_used_key
from explosion
