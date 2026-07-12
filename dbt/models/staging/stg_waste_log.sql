with source as (

    select * from {{ source('raw', 'waste_log') }}

),

cleaned as (

    select
        store_id,
        item_id,
        quantity::integer                   as quantity,
        created_at::timestamp               as created_at,
        created_at::date                    as waste_date,
        extract(hour from created_at)       as waste_hour,

        -- day_of_week flag
        dayofweekiso(created_at) - 1        as day_of_week

    from source

)

select * from cleaned