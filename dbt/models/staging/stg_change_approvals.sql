with source as (

    select * from {{ source('plm', 'change_approvals') }}

),

renamed as (

    select
        trim(approval_id) as approval_id,
        trim(change_id) as change_id,
        lower(trim(approver_role)) as approver_role,
        lower(trim(decision)) as decision,
        try_cast(
            nullif(trim(cast(decided_at as varchar)), '') as date
        ) as decided_at
    from source

)

select * from renamed
