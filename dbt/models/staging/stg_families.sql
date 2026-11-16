with source as (

    select * from {{ source('plm', 'families') }}

),

renamed as (

    select
        trim(family_id) as family_id,
        trim(family_name) as family_name
    from source

)

select * from renamed
