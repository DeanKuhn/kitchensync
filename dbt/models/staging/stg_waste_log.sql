with source as (

    -- First get the source using Jinja formatting
    select * from {{ source('raw', 'waste_log') }}

),


cleaned as (

    select
        store_id,
        item_id,
        quantity::integer       as quantity,
        reason,
        created_at::timestamp   as created_at,
        created_at::date        as waste_date,

    from source

    where created_at is not null

)


select * from cleaned