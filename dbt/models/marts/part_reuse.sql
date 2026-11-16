-- Part reuse profile as of as_of_date.
--
-- One row per part. direct_parent_count and total_direct_quantity come from
-- BOM lines that are effective on as_of_date and whose parent revision is the
-- current released revision (the same rule int_bom_explosion uses).
-- product_count counts the distinct products that reach the part.
-- Parts that are used nowhere still appear, with zero counts.

{% set as_of_date = var('as_of_date', '2026-06-01') %}

with active_boms as (

    select
        b.child_part_id,
        b.parent_part_id,
        b.quantity
    from {{ ref('stg_boms') }} as b
    inner join {{ ref('int_current_revisions') }} as cr
        on cr.part_id = b.parent_part_id
       and cr.revision_id = b.parent_revision_id
    where date '{{ as_of_date }}' between b.effectivity_start
        and coalesce(b.effectivity_end, date '9999-12-31')

),

direct as (

    select
        child_part_id,
        count(distinct parent_part_id) as direct_parent_count,
        sum(quantity) as total_direct_quantity
    from active_boms
    group by child_part_id

),

product_usage as (

    select
        child_part_id,
        count(distinct product_id) as product_count
    from (
        -- Parts reached below the product top assembly.
        select child_part_id, product_id
        from {{ ref('int_where_used') }}
        union
        -- Each product's own top-level part is used by that product too.
        select top_level_part_id as child_part_id, product_id
        from {{ ref('stg_products') }}
    )
    group by child_part_id

)

select
    p.part_id,
    p.name as part_name,
    p.part_type,
    p.family_id,
    cast(coalesce(d.direct_parent_count, 0) as integer) as direct_parent_count,
    cast(coalesce(u.product_count, 0) as integer) as product_count,
    cast(coalesce(d.total_direct_quantity, 0) as decimal(18, 4))
        as total_direct_quantity
from {{ ref('stg_parts') }} as p
left join direct as d
    on d.child_part_id = p.part_id
left join product_usage as u
    on u.child_part_id = p.part_id
