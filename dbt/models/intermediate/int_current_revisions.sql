-- The released revision of each part that is effective on as_of_date.
--
-- Clean data has exactly one released revision per part. Defective data can
-- have overlapping released revisions; when that happens the winner is chosen
-- deterministically by latest effective_from, then revision_code. The
-- effective_to coalesce keeps open-ended revisions eligible.

{% set as_of_date = var('as_of_date', '2026-06-01') %}

with released as (

    select
        part_id,
        revision_id,
        revision_code,
        status,
        effective_from,
        effective_to
    from {{ ref('stg_part_revisions') }}
    where status = 'released'
      and date '{{ as_of_date }}' between effective_from
          and coalesce(effective_to, date '9999-12-31')

),

ranked as (

    select
        *,
        row_number() over (
            partition by part_id
            order by effective_from desc, revision_code desc, revision_id desc
        ) as revision_rank
    from released

)

select
    part_id,
    revision_id,
    revision_code,
    status,
    effective_from,
    effective_to
from ranked
where revision_rank = 1
