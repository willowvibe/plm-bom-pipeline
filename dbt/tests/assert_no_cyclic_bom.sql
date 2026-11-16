-- Fails when any BOM edge closes a cycle.
--
-- Walks the BOM graph from every line. The recursive step records an edge as
-- closing a cycle when its child is already on the walked path; that edge is
-- emitted and the walk stops there. A depth guard bounds pathological input.
-- Returns distinct (start, parent, child) triples for the closing edges.

with recursive walk as (

    select
        b.parent_part_id as start_part_id,
        b.parent_part_id,
        b.child_part_id,
        cast(array_value(b.parent_part_id, b.child_part_id) as varchar[]) as path,
        1 as depth,
        b.parent_part_id = b.child_part_id as closes_cycle
    from {{ ref('stg_boms') }} as b

    union all

    select
        w.start_part_id,
        b.parent_part_id,
        b.child_part_id,
        list_append(w.path, b.child_part_id),
        w.depth + 1,
        list_contains(w.path, b.child_part_id)
    from walk as w
    inner join {{ ref('stg_boms') }} as b
        on b.parent_part_id = w.child_part_id
    where w.depth < 30
      and not w.closes_cycle

)

select distinct
    start_part_id,
    parent_part_id,
    child_part_id
from walk
where closes_cycle
