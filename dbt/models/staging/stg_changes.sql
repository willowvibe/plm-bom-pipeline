with source as (

    select * from {{ source('plm', 'changes') }}

),

renamed as (

    select
        trim(change_id) as change_id,
        lower(trim(change_type)) as change_type,
        nullif(trim(parent_change_id), '') as parent_change_id,
        trim(title) as title,
        lower(trim(status)) as status,
        cast(initiated_at as date) as initiated_at,
        try_cast(
            nullif(trim(cast(approved_at as varchar)), '') as date
        ) as approved_at,
        try_cast(
            nullif(trim(cast(closed_at as varchar)), '') as date
        ) as closed_at,
        trim(affected_part_id) as affected_part_id
    from source

)

select * from renamed
