with rolling as (

    select * from {{ ref('int_sales__rolling_features_15min') }}

),


profile as (

    select * from {{ ref('int_sales__time_of_day_profile') }}

),


final as (

    select
        r.store_id,
        r.item_id,
        r.sale_date,
        r.sale_hour,
        r.slot_index,
        r.day_of_week,
        r.slot_quantity,
        p.avg_slot_quantity,
        p.sample_size

    from rolling r
    left join profile p
        on r.store_id       = p.store_id
        and r.item_id       = p.item_id
        and r.day_of_week   = p.day_of_week
        and r.sale_hour     = p.sale_hour

)


select * from final