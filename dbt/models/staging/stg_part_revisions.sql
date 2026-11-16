with source as (

    select * from {{ source('plm', 'part_revisions') }}

),

renamed as (

    select
        trim(revision_id) as revision_id,
        trim(part_id) as part_id,
        upper(trim(revision_code)) as revision_code,
        lower(trim(status)) as status,
        cast(effective_from as date) as effective_from,
        try_cast(
            nullif(trim(cast(effective_to as varchar)), '') as date
        ) as effective_to
    from source

)

select * from renamed
