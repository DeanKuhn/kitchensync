with sales as (

    select * from {{ ref('stg_sales_events') }}

),


slotly as (

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


rolling as (

    select
        store_id,
        item_id,
        sale_date,
        sale_hour,
        slot_index,
        day_of_week,
        slot_quantity

    from slotly

)


select * from rolling