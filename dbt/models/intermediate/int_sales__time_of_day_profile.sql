--  === BUCKET BEGIN ===

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

-- === BUCKET DONE ===


-- int_sales__time_of_day_profile is cross-date average,
-- computing avg_slot_quantity and sample_size

-- total observed days per store/day_of_week — used as denominator
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


-- total distinct sales dates per item and store
distinct_sales as (

    select
        store_id,
        item_id,
        count(distinct sale_date) as days_observed

    from sales

    group by
        store_id,
        item_id
),


-- profile, all data summed up
profile as (

    select
        f.store_id,
        f.item_id,
        f.day_of_week,
        f.sale_hour,
        f.slot_index,
        sum(f.quantity) / t.total_dates  as avg_slot_quantity,
        count(*)                          as sample_size,
        d.days_observed

    from fifteen_min f
    join total_days t
        on  f.store_id    = t.store_id
        and f.day_of_week = t.day_of_week
    join distinct_sales d
        on  f.store_id    = d.store_id
        and f.item_id     = d.item_id

    group by
        f.store_id,
        f.item_id,
        f.sale_hour,
        f.slot_index,
        f.day_of_week,
        t.total_dates,
        d.days_observed

)

select * from profile