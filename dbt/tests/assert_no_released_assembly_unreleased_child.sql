-- Fails when a BOM line of a released assembly revision points at a child
-- revision that is not released. A released assembly must only consume
-- released child revisions.

select
    b.bom_line_id,
    b.parent_part_id,
    b.parent_revision_id,
    parent_revision.status as parent_revision_status,
    b.child_part_id,
    b.child_revision_id,
    child_revision.status as child_revision_status
from {{ ref('stg_boms') }} as b
inner join {{ ref('stg_parts') }} as parent_part
    on parent_part.part_id = b.parent_part_id
   and parent_part.part_type = 'assembly'
inner join {{ ref('stg_part_revisions') }} as parent_revision
    on parent_revision.revision_id = b.parent_revision_id
   and parent_revision.status = 'released'
inner join {{ ref('stg_part_revisions') }} as child_revision
    on child_revision.revision_id = b.child_revision_id
where child_revision.status <> 'released'
