-- Recursive multi-level BOM explosion as of as_of_date.
--
-- One row per product traversal path: the level-0 product top assembly plus
-- every reachable child at levels 1..N. quantity is the direct BOM line
-- quantity; accumulated_quantity multiplies the quantities down the path, so
-- it is the number of child units required to build one product.
--
-- A BOM line is followed only when:
--   * its effectivity window contains as_of_date, and
--   * its parent revision is the current released revision of the parent part.
-- path_parts is carried through the recursion as a cycle guard: a child that
-- already appears on the path is never revisited, so a cyclic BOM terminates.

{% set as_of_date = var('as_of_date', '2026-06-01') %}
{% set max_bom_depth = var('max_bom_depth', 20) %}

with recursive explosion as (

    select
        p.product_id,
        p.top_level_part_id as root_part_id,
        0 as level,
        cast(array_value(p.top_level_part_id) as varchar[]) as path_parts,
        cast(null as varchar) as parent_part_id,
        p.top_level_part_id as child_part_id,
        cast(1 as decimal(18, 6)) as quantity,
        cast(1 as decimal(18, 6)) as accumulated_quantity
    from {{ ref('stg_products') }} as p

    union all

    select
        e.product_id,
        e.root_part_id,
        e.level + 1,
        list_append(e.path_parts, b.child_part_id),
        b.parent_part_id,
        b.child_part_id,
        cast(b.quantity as decimal(18, 6)),
        cast(e.accumulated_quantity * b.quantity as decimal(18, 6))
    from explosion as e
    inner join {{ ref('stg_boms') }} as b
        on b.parent_part_id = e.child_part_id
    inner join {{ ref('int_current_revisions') }} as cr
        on cr.part_id = b.parent_part_id
       and cr.revision_id = b.parent_revision_id
    where e.level < {{ max_bom_depth }}
      and date '{{ as_of_date }}' between b.effectivity_start
          and coalesce(b.effectivity_end, date '9999-12-31')
      and not list_contains(e.path_parts, b.child_part_id)

)

select
    product_id,
    root_part_id,
    level,
    array_to_string(path_parts, ' > ') as path,
    parent_part_id,
    child_part_id,
    quantity,
    accumulated_quantity
from explosion
order by product_id, path
