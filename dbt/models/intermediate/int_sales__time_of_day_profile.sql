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
        sum(quantity) as quantity

    from sales

    group by
        store_id,
        item_id,
        sale_date,
        sale_hour,
        slot_index,
        day_of_week

),


profile as (

    select
        store_id,
        item_id,
        day_of_week,
        sale_hour,
        slot_index,
        avg(quantity) as avg_slot_quantity,
        count(*) as sample_size

    from fifteen_min

    group by
        store_id,
        item_id,
        sale_hour,
        slot_index,
        day_of_week

)


select * from profile