with source as (

    select * from {{ source('plm', 'boms') }}

),

renamed as (

    select
        trim(bom_line_id) as bom_line_id,
        trim(parent_part_id) as parent_part_id,
        trim(parent_revision_id) as parent_revision_id,
        trim(child_part_id) as child_part_id,
        trim(child_revision_id) as child_revision_id,
        cast(quantity as decimal(18, 4)) as quantity,
        trim(uom) as uom,
        cast(find_number as integer) as find_number,
        cast(effectivity_start as date) as effectivity_start,
        try_cast(
            nullif(trim(cast(effectivity_end as varchar)), '') as date
        ) as effectivity_end
    from source

)

select * from renamed
