with source as (

    select * from {{ source('plm', 'products') }}

),

renamed as (

    select
        trim(product_id) as product_id,
        trim(family_id) as family_id,
        trim(name) as name,
        cast(model_year as integer) as model_year,
        trim(top_level_part_id) as top_level_part_id
    from source

)

select * from renamed
