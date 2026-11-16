-- Product impact of engineering changes.
--
-- One row per distinct (change, product) pair. A product is impacted when:
--   * it reaches the change's affected part through int_where_used (the part
--     is used somewhere below the product top assembly), or
--   * the affected part is the product's own top-level part.
-- Both routes are unioned and deduplicated so a product appears once per
-- change even when the part is reachable through several BOM paths.

with via_where_used as (

    select distinct
        c.change_id,
        wu.product_id
    from {{ ref('stg_changes') }} as c
    inner join {{ ref('int_where_used') }} as wu
        on wu.child_part_id = c.affected_part_id

),

via_top_level as (

    select distinct
        c.change_id,
        p.product_id
    from {{ ref('stg_changes') }} as c
    inner join {{ ref('stg_products') }} as p
        on p.top_level_part_id = c.affected_part_id

),

impact as (

    select change_id, product_id from via_where_used
    union
    select change_id, product_id from via_top_level

)

select
    i.change_id,
    c.change_type,
    c.status,
    c.title,
    c.affected_part_id,
    i.product_id,
    p.name as product_name,
    p.family_id,
    i.change_id || '|' || i.product_id as change_product_key
from impact as i
inner join {{ ref('stg_changes') }} as c
    on c.change_id = i.change_id
inner join {{ ref('stg_products') }} as p
    on p.product_id = i.product_id
