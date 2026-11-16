-- Fails when two released revisions of the same part have overlapping
-- effectivity windows. An empty effective_to is open-ended (9999-12-31).
-- Windows that merely touch on a single date are not overlaps.

with released as (

    select
        part_id,
        revision_id,
        effective_from,
        coalesce(effective_to, date '9999-12-31') as effective_to
    from {{ ref('stg_part_revisions') }}
    where status = 'released'

)

select
    a.part_id,
    a.revision_id as revision_id_a,
    b.revision_id as revision_id_b,
    a.effective_from as effective_from_a,
    a.effective_to as effective_to_a,
    b.effective_from as effective_from_b,
    b.effective_to as effective_to_b
from released as a
inner join released as b
    on a.part_id = b.part_id
   and a.revision_id < b.revision_id
where a.effective_from < b.effective_to
  and b.effective_from < a.effective_to
