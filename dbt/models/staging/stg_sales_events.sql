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
        extract(dayofweek from created_at)                  as day_of_week,
        time_slice(created_at::timestamp, 15, 'MINUTE')     as sale_15min,
        extract(minute from sale_15min)                     as sale_minute

    from source

)


select * from cleaned


/*

--- DATA TRANSFORMATION VISUALIZATION ---

RAW SOURCE (sales_events)
STORE_ID | ITEM_ID | QUANTITY | CREATED_AT
store_01 | BURGER  | 2        | 2026-02-12 12:05:00.000

STAGING (stg_sales_events)
STORE_ID | ITEM_ID | QUANTITY (int) | SALE_DATE  | SALE_HOUR | DAY_OF_WEEK
store_01 | BURGER  | 2              | 2026-02-12 | 12        | 4 (Thursday)

*/