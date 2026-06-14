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


/*

--- DATA TRANSFORMATION VISUALIZATION ---

STEP 1: stg_stockout_events (Granular Events)
ITEM_ID | STOCKOUT_HOUR | QTY_REQUESTED
BURGER  | 12            | 2
BURGER  | 12            | 3

STEP 2: mart_stockout_summary (Hourly Aggregation)
ITEM_ID | STOCKOUT_HOUR | TOTAL_MISSED_UNITS | EVENT_COUNT
BURGER  | 12            | 5                  | 2

*/