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
        extract(dayofweek from created_at)  as day_of_week

    from source

)


select * from cleaned


/*

--- DATA TRANSFORMATION VISUALIZATION ---

RAW SOURCE (stockout_events)
STORE_ID | ITEM_ID | QTY_REQUESTED | CREATED_AT
store_01 | BURGER  | 3             | 2026-02-12 12:30:00.000

STAGING (stg_stockout_events)
STORE_ID | ITEM_ID | QTY_REQUESTED | STOCKOUT_DATE | STOCKOUT_HOUR | DAY_OF_WEEK
store_01 | BURGER  | 3             | 2026-02-12    | 12            | 4

*/
