-- Fails when a closed ECO has no ECN child referencing it. Every closed
-- implementation order must have issued a corresponding engineering change
-- notice in clean data.

select
    c.change_id,
    c.change_type,
    c.status,
    c.parent_change_id,
    c.initiated_at,
    c.closed_at
from {{ ref('stg_changes') }} as c
where c.change_type = 'eco'
  and c.status = 'closed'
  and not exists (
      select 1
      from {{ ref('stg_changes') }} as ecn
      where ecn.change_type = 'ecn'
        and ecn.parent_change_id = c.change_id
  )
