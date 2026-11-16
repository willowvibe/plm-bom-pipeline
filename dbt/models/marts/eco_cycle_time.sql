-- Engineering change cycle times.
--
-- One row per change. Day counts are null when the corresponding date is
-- missing (for example an open change has no approval or close date), so this
-- model never invents a duration. cycle_status summarises the furthest point
-- reached in the lifecycle.

select
    change_id,
    change_type,
    parent_change_id,
    title,
    status,
    affected_part_id,
    initiated_at,
    approved_at,
    closed_at,
    date_diff('day', initiated_at, approved_at) as days_to_approval,
    date_diff('day', initiated_at, closed_at) as days_to_close,
    case
        when closed_at is not null then 'closed'
        when status = 'rejected' then 'rejected'
        when approved_at is not null then 'approved'
        else 'open'
    end as cycle_status
from {{ ref('stg_changes') }}
