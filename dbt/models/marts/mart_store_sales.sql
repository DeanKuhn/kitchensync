with rolling as (

    select * from {{ ref('int_sales__rolling_features') }}

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
        r.day_of_week,
        r.hourly_quantity,
        r.rolling_2hr,
        r.rolling_4hr,
        p.avg_hourly_quantity,
        p.sample_size

    from rolling r
    left join profile p
        on r.store_id       = p.store_id
        and r.item_id       = p.item_id
        and r.day_of_week   = p.day_of_week
        and r.sale_hour     = p.sale_hour

)


select * from final


/*

--- DATA TRANSFORMATION VISUALIZATION ---

STEP 1: rolling (The "Now" data - current performance)
STORE_ID | ITEM_ID | SALE_HOUR | ROLLING_2HR | ROLLING_4HR
store_01 | BURGER  | 12        | 15          | 25

STEP 2: profile (The "Historical" data - what usually happens)
STORE_ID | ITEM_ID | SALE_HOUR | AVG_HOURLY_QUANTITY | SAMPLE_SIZE
store_01 | BURGER  | 12        | 10                  | 40

STEP 3: final (The Feature Store for ML)
ITEM_ID | ROLLING_2HR | AVG_HOURLY_QUANTITY | COMPARISON
BURGER  | 15          | 10                  | Current is 1.5x history

*/