with sales as (

    select * from {{ ref('stg_sales_events') }}

),


minutely as (

    select
        store_id,
        item_id,
        sale_date,
        sale_hour,
        sale_minute,
        (day_of_week * 96) + (sale_hour * 4) + FLOOR(sale_minute / 15) as slot_index,
        day_of_week,
        sum(quantity) as slot_quantity

    from sales

    group by
        store_id,
        item_id,
        sale_date,
        sale_hour,
        sale_minute,
        day_of_week

),


rolling as (

    select
        store_id,
        item_id,
        sale_date,
        sale_hour,
        sale_minute,
        slot_index,
        day_of_week,
        slot_quantity

    from minutely

)


select * from rolling


/*

--- DATA TRANSFORMATION VISUALIZATION ---

STEP 1: stg_sales_events (Raw Events)
STORE_ID | ITEM_ID | CREATED_AT          | QTY
store_01 | BURGER  | 2026-02-12 12:05:00 | 2
store_01 | BURGER  | 2026-02-12 12:45:00 | 3

STEP 2: minutely (Aggregated by 15-min slot)
STORE_ID | ITEM_ID | SALE_HOUR | SALE_MINUTE | SLOT_INDEX | SLOT_QUANTITY
store_01 | BURGER  | 12        | 0           | 48         | 3
store_01 | BURGER  | 12        | 15          | 49         | 2
store_01 | BURGER  | 12        | 30          | 50         | 4
store_01 | BURGER  | 12        | 45          | 51         | 1

STEP 3: rolling (Window Functions Applied)
STORE_ID | ITEM_ID | SLOT_INDEX | SLOT_QUANTITY
store_01 | BURGER  | 48         | 3
store_01 | BURGER  | 49         | 2
store_01 | BURGER  | 50         | 4
store_01 | BURGER  | 51         | 1
store_01 | BURGER  | 52         | 5

*/