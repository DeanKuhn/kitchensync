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
        extract(dayofweek from created_at)   as day_of_week

    from source

)


select * from cleaned


/*

--- DATA TRANSFORMATION VISUALIZATION ---

RAW SOURCE (waste_log)
STORE_ID | ITEM_ID | QUANTITY | CREATED_AT
store_01 | BURGER  | 5        | 2026-02-12 14:00:00.000

STAGING (stg_waste_log)
STORE_ID | ITEM_ID | QUANTITY (int) | WASTE_DATE | WASTE_HOUR | DAY_OF_WEEK
store_01 | BURGER  | 5              | 2026-02-12 | 14         | 4

*/