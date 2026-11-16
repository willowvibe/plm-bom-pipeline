with source as (

    select * from {{ source('plm', 'erp_bom') }}

),

renamed as (

    select
        trim(parent_part_number) as parent_part_number,
        trim(child_part_number) as child_part_number,
        cast(quantity as decimal(18, 4)) as quantity,
        trim(uom) as uom
    from source

)

select * from renamed
