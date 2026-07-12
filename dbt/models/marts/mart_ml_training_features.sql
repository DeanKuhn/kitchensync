with profile as (

    select * from {{ ref('int_sales__time_of_day_profile') }}

),

rolling as (

    select * from {{ ref('int_sales__rolling_features_15min') }}

),

store_dates as (

    select distinct store_id, sale_date
    from {{ ref('stg_sales_events') }}

),

-- active (store, item, slot) combinations joined to all matching dates,
-- starting from the profile means we only generate rows for slots where
-- the item has actually sold at some point, so no phantom zeros for
-- closed-store overnight hours or items that never move in that window
spine as (

    select
        p.store_id,
        p.item_id,
        sd.sale_date,
        p.day_of_week,
        p.sale_hour,
        (p.slot_index % 4) * 15 as sale_minute,
        p.slot_index,
        p.avg_slot_quantity,
        p.sample_size

    from profile p
    inner join store_dates sd
        on  p.store_id                     = sd.store_id
        -- day_of_week flag
        and dayofweekiso(sd.sale_date) - 1 = p.day_of_week

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
        coalesce(r.slot_quantity, 0) as slot_quantity,
        s.avg_slot_quantity,
        s.sample_size

    from spine s
    left join rolling r
        on  s.store_id   = r.store_id
        and s.item_id    = r.item_id
        and s.sale_date  = r.sale_date
        and s.slot_index = r.slot_index

)

select * from final
