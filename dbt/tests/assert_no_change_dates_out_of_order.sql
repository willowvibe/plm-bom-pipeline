select *
from {{ ref('stg_changes') }}
where
    (approved_at is not null and approved_at < initiated_at)
    or
    (closed_at is not null and approved_at is not null
     and closed_at < approved_at)
