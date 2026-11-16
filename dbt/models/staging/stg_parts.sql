with source as (

    select * from {{ source('plm', 'parts') }}

),

renamed as (

    select
        trim(part_id) as part_id,
        trim(part_number) as part_number,
        trim(name) as name,
        lower(trim(part_type)) as part_type,
        trim(family_id) as family_id,
        trim(uom) as uom,
        lower(trim(lifecycle_state)) as lifecycle_state,
        cast(standard_cost as decimal(12, 2)) as standard_cost,
        cast(created_at as date) as created_at
    from source

)

select * from renamed
