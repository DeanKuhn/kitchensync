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

-- Total observed days per store/day_of_week — used as denominator so that
-- zero-sale slots are included in the average (not just days with actual sales).
total_days as (

    select
        store_id,
        day_of_week,
        count(distinct sale_date) as total_dates

    from sales

    group by
        store_id,
        day_of_week

),

profile as (

    select
        f.store_id,
        f.item_id,
        f.day_of_week,
        f.sale_hour,
        f.slot_index,
        sum(f.quantity) / t.total_dates  as avg_slot_quantity,
        count(*)                          as sample_size

    from fifteen_min f
    join total_days t
        on  f.store_id    = t.store_id
        and f.day_of_week = t.day_of_week

    group by
        f.store_id,
        f.item_id,
        f.sale_hour,
        f.slot_index,
        f.day_of_week,
        t.total_dates

)


select * from profile