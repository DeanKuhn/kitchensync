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
        and r.slot_index    = p.slot_index

    qualify row_number() over (
        partition by r.store_id, r.item_id
        order by r.sale_date desc, r.sale_hour desc, r.slot_index desc
    ) = 1

)


select * from final


/*

--- DATA TRANSFORMATION VISUALIZATION ---

STEP 1: rolling (The "Now" data - current 15-min performance)
STORE_ID | ITEM_ID | SLOT_INDEX | SLOT_QUANTITY
store_01 | BURGER  | 49         | 3

STEP 2: profile (The "Historical" data - avg demand for this slot)
STORE_ID | ITEM_ID | SLOT_INDEX | AVG_SLOT_QUANTITY   | SAMPLE_SIZE
store_01 | BURGER  | 49         | 2.8                 | 42

STEP 3: final (The 15-min Feature Store for ML)
STORE_ID | ITEM_ID | SLOT_INDEX | SLOT_QUANTITY | AVG_SLOT_QUANTITY
store_01 | BURGER  | 49         | 3             | 2.8
(QUALIFY keeps only the most recent slot per store/item)

*/