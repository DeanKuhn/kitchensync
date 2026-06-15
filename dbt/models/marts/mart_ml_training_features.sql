with store_dates as (

    select distinct store_id, sale_date
    from {{ ref('stg_sales_events') }}

),


items as (

    select distinct item_id
    from {{ ref('stg_sales_events') }}

),


-- 96 slots per day (0–95), generated via Snowflake row generator
slot_spine as (

    select (row_number() over (order by seq4())) - 1 as slot_within_day
    from table(generator(rowcount => 96))

),


-- Full grid: every store × item × date × slot combination
spine as (

    select
        sd.store_id,
        sd.sale_date,
        i.item_id,
        sl.slot_within_day,
        dayofweekiso(sd.sale_date) - 1                                as day_of_week,
        sl.slot_within_day // 4                                        as sale_hour,
        (sl.slot_within_day % 4) * 15                                  as sale_minute,
        ((dayofweekiso(sd.sale_date) - 1) * 96) + sl.slot_within_day  as slot_index

    from store_dates sd
    cross join items i
    cross join slot_spine sl

),


rolling as (

    select * from {{ ref('int_sales__rolling_features_15min') }}

),


profile as (

    select * from {{ ref('int_sales__time_of_day_profile') }}

),


final as (

    select
        s.store_id,
        s.item_id,
        s.sale_date,
        s.sale_hour,
        s.sale_minute,
        s.slot_index,
        s.day_of_week,
        coalesce(r.slot_quantity, 0)      as slot_quantity,
        coalesce(p.avg_slot_quantity, 0)  as avg_slot_quantity,
        coalesce(p.sample_size, 0)        as sample_size

    from spine s
    left join rolling r
        on  s.store_id    = r.store_id
        and s.item_id     = r.item_id
        and s.sale_date   = r.sale_date
        and s.slot_index  = r.slot_index
    left join profile p
        on  s.store_id    = p.store_id
        and s.item_id     = p.item_id
        and s.day_of_week = p.day_of_week
        and s.sale_hour   = p.sale_hour
        and s.slot_index  = p.slot_index

)


select * from final
