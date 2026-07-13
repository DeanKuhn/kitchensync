-- === BUCKET BEGIN ===

with sales as (

    select * from {{ ref('stg_sales_events') }}

),


fifteen_min as (

    select
        store_id,
        item_id,
        sale_date,
        sale_hour,
        (day_of_week * 96) + (sale_hour * 4) + FLOOR(sale_minute / 15) as slot_index,
        day_of_week,
        sum(quantity) as slot_quantity

    from sales

    group by
        store_id,
        item_id,
        sale_date,
        sale_hour,
        slot_index,
        day_of_week

),

-- === BUCKET DONE ===


-- int_sales__rolling_features_15min is
-- event-level history compressed to slot-grain
rolling as (

    select
        store_id,
        item_id,
        sale_date,
        sale_hour,
        slot_index,
        day_of_week,
        slot_quantity

    from fifteen_min

)

select * from rolling