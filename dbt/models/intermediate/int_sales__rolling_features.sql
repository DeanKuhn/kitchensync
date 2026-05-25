with sales as (

    select * from {{ ref('stg_sales_events') }}

),


hourly as (

    select
        store_id,
        item_id,
        sale_date,
        sale_hour,
        day_of_week,
        sum(quantity) as hourly_quantity

    from sales

    group by
        store_id,
        item_id,
        sale_date,
        sale_hour,
        day_of_week

),


rolling as (

    select
        store_id,
        item_id,
        sale_date,
        sale_hour,
        day_of_week,
        hourly_quantity,

        sum(hourly_quantity) over (
            partition by store_id, item_id
            order by sale_date, sale_hour
            rows between 1 preceding and current row
        ) as rolling_2hr,

        sum(hourly_quantity) over (
            partition by store_id, item_id
            order by sale_date, sale_hour
            rows between 3 preceding and current row
        ) as rolling_4hr

    from hourly

)


select * from rolling


/*

--- DATA TRANSFORMATION VISUALIZATION ---

STEP 1: stg_sales_events (Raw Events)
STORE_ID | ITEM_ID | CREATED_AT          | QTY
store_01 | BURGER  | 2026-02-12 12:05:00 | 2
store_01 | BURGER  | 2026-02-12 12:45:00 | 3

STEP 2: hourly (Aggregated by Hour)
STORE_ID | ITEM_ID | SALE_HOUR | HOURLY_QUANTITY
store_01 | BURGER  | 12        | 5
store_01 | BURGER  | 13        | 8

STEP 3: rolling (Window Functions Applied)
STORE_ID | ITEM_ID | SALE_HOUR | HOURLY_QUANTITY | ROLLING_2HR | ROLLING_4HR
store_01 | BURGER  | 12        | 5               | 5           | 5
store_01 | BURGER  | 13        | 8               | 13          | 13
store_01 | BURGER  | 14        | 10              | 18          | 23

*/