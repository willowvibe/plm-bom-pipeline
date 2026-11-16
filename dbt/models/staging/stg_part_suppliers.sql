with source as (

    select * from {{ source('plm', 'part_suppliers') }}

),

renamed as (

    select
        trim(part_id) as part_id,
        trim(supplier_id) as supplier_id,
        cast(unit_price as decimal(12, 2)) as unit_price,
        cast(lead_time_days as integer) as lead_time_days,
        trim(part_id) || '|' || trim(supplier_id) as part_supplier_key
    from source

)

select * from renamed
