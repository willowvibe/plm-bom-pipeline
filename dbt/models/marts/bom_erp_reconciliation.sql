-- PLM versus ERP BOM reconciliation as of as_of_date.
--
-- The PLM side aggregates the active BOM lines by parent/child part number
-- (the ERP extract is keyed by part number) and sums line quantities. The ERP
-- side aggregates its extract the same way. The two sides are full outer
-- joined on the parent/child part-number key, so one row is produced for
-- every key present in either system. When a key has several UoMs the
-- lexicographically smallest one is used as the representative value.
--
-- reconciliation_status is one of:
--   match              both sides present, same quantity and UoM
--   quantity_mismatch  both sides present, quantities differ
--   uom_mismatch       both sides present, representative UoMs differ
--   plm_only           only the PLM BOM has the key
--   erp_only           only the ERP extract has the key

{% set as_of_date = var('as_of_date', '2026-06-01') %}

with plm_lines as (

    select
        parent.part_number as parent_part_number,
        child.part_number as child_part_number,
        b.quantity,
        b.uom
    from {{ ref('stg_boms') }} as b
    inner join {{ ref('stg_parts') }} as parent
        on parent.part_id = b.parent_part_id
    inner join {{ ref('stg_parts') }} as child
        on child.part_id = b.child_part_id
    inner join {{ ref('int_current_revisions') }} as cr
        on cr.part_id = b.parent_part_id
       and cr.revision_id = b.parent_revision_id
    where date '{{ as_of_date }}' between b.effectivity_start
        and coalesce(b.effectivity_end, date '9999-12-31')

),

plm as (

    select
        parent_part_number,
        child_part_number,
        sum(quantity) as plm_quantity,
        min(uom) as plm_uom
    from plm_lines
    group by parent_part_number, child_part_number

),

erp as (

    select
        parent_part_number,
        child_part_number,
        sum(quantity) as erp_quantity,
        min(uom) as erp_uom
    from {{ ref('stg_erp_bom') }}
    group by parent_part_number, child_part_number

),

joined as (

    select
        coalesce(plm.parent_part_number, erp.parent_part_number)
            as parent_part_number,
        coalesce(plm.child_part_number, erp.child_part_number)
            as child_part_number,
        plm.plm_quantity,
        erp.erp_quantity,
        plm.plm_uom,
        erp.erp_uom,
        cast(
            coalesce(plm.plm_quantity, 0) - coalesce(erp.erp_quantity, 0)
            as decimal(18, 4)
        ) as quantity_delta,
        case
            when plm.parent_part_number is null then 'erp_only'
            when erp.parent_part_number is null then 'plm_only'
            when plm.plm_uom <> erp.erp_uom then 'uom_mismatch'
            when plm.plm_quantity <> erp.erp_quantity then 'quantity_mismatch'
            else 'match'
        end as reconciliation_status
    from plm
    full outer join erp
        on plm.parent_part_number = erp.parent_part_number
       and plm.child_part_number = erp.child_part_number

)

select
    parent_part_number || '|' || child_part_number as reconciliation_key,
    *
from joined
