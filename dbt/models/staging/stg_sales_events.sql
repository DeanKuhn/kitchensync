with source as (

    select * from {{ source('raw', 'sales_events') }}

),

cleaned as (

    select
        store_id,
        item_id,
        quantity::integer                                   as quantity,
        price::float                                        as price,
        created_at::timestamp                               as created_at,
        created_at::date                                    as sale_date,
        extract(hour from created_at)                       as sale_hour,

        -- day_of_week flag
        dayofweekiso(created_at) - 1                        as day_of_week,
        time_slice(created_at::timestamp, 15, 'MINUTE')     as sale_15min,
        extract(minute from sale_15min)                     as sale_minute

    from source

)

select * from cleaned