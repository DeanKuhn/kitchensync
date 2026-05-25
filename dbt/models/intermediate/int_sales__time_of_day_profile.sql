with sales as (

    select * from {{ ref('stg_sales_events') }}

),


fifteen_min as (

    select
        store_id,
        item_id,
        sale_date,
        sale_hour,
        sale_minute,
        day_of_week,
        sum(quantity) as quantity

    from sales

    group by
        store_id,
        item_id,
        sale_date,
        sale_hour,
        sale_minute,
        day_of_week

),


profile as (

    select
        store_id,
        item_id,
        day_of_week,
        sale_hour,
        sale_minute,
        avg(quantity) as avg_hourly_quantity,
        count(*) as sample_size

    from fifteen_min

    group by
        store_id,
        item_id,
        day_of_week,
        sale_hour,
        sale_minute

)


select * from profile


/*

--- DATA TRANSFORMATION VISUALIZATION ---

STEP 1: fifteen_min (Aggregated by 15-minute blocks)
STORE_ID | ITEM_ID | SALE_HOUR | SALE_MINUTE | QUANTITY
store_01 | BURGER  | 12        | 0           | 3
store_01 | BURGER  | 12        | 15          | 2

STEP 2: profile (Historical averages per 15-min block)
STORE_ID | ITEM_ID | DAY_OF_WEEK | HOUR | MINUTE | AVG_HOURLY_QUANTITY
store_01 | BURGER  | 1 (Mon)     | 12   | 0      | 2.8
*/