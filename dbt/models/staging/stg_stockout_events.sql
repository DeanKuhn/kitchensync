with source as (

    select * from {{ source('raw', 'stockout_events') }}

),

cleaned as (

    select
        store_id,
        item_id,
        quantity_requested::integer         as quantity_requested,
        created_at::timestamp               as created_at,
        created_at::date                    as stockout_date,
        extract(hour from created_at)       as stockout_hour,

        -- day_of_week flag
        dayofweekiso(created_at) - 1        as day_of_week

    from source

)

select * from cleaned