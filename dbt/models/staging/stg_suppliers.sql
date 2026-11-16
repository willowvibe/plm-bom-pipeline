with source as (

    select * from {{ source('plm', 'suppliers') }}

),

renamed as (

    select
        trim(supplier_id) as supplier_id,
        trim(name) as name,
        trim(country) as country
    from source

)

select * from renamed
