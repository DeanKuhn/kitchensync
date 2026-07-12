with stockouts as (

    select * from {{ ref('stg_stockout_events') }}

),

final as (

    select
        store_id,
        item_id,
        stockout_date,
        stockout_hour,
        day_of_week,
        sum(quantity_requested) as total_missed_units,
        count(*)                as event_count

    from stockouts

    group by
        store_id,
        item_id,
        stockout_date,
        stockout_hour,
        day_of_week

)

select * from final