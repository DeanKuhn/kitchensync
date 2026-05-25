with menu as (

    select
        item_id,
        hold_time

    from {{ ref('menu_items') }}

),


profile as (

    select * from {{ ref('int_sales__time_of_day_profile') }}

),


base_slots as (

    select
        p.*,
        m.hold_time,
        (m.hold_time * 4) as slots_to_look_ahead,
        (p.day_of_week * 96) + (p.sale_hour * 4) + (p.sale_minute / 15)
            as slot_index

    from profile p
    join menu m on p.item_id = m.item_id

),


expanded_slots as (

    select * from base_slots
    union all
    select
        * exclude (slot_index),
        slot_index + 672 as slot_index
    from base_slots

),


final as (

    select
        a.store_id,
        a.item_id,
        a.day_of_week,
        a.sale_hour,
        a.sale_minute,
        a.slot_index,
        sum(b.avg_hourly_quantity) as target_inventory

    from base_slots a
    join expanded_slots b
        on a.store_id = b.store_id
        and a.item_id = b.item_id

        and b.slot_index >= a.slot_index
        and b.slot_index < (a.slot_index + a.slots_to_look_ahead)

    group by 1, 2, 3, 4, 5, 6

)


select * from final


/*

--- DATA TRANSFORMATION VISUALIZATION ---

STEP 1: base_slots (15-min grain + slot_index 0-671)
ITEM_ID | HOUR | MIN | SLOT_INDEX | AVG_QTY | HOLD_TIME (SLOTS)
BURGER  | 12   | 0   | 240        | 1.5     | 8 (2 hrs)

STEP 2: expanded_slots (Doubled data to 1343 slots for wrap-around)
(Simulates the 'next week' so the join never hits a wall)

STEP 3: final (The Sliding Window Sum)
ITEM_ID | HOUR | MIN | SLOT_INDEX | PREDICTED_UNITS
BURGER  | 12   | 0   | 240        | 12.4 (Sum of next 8 slots)
BURGER  | 12   | 15  | 241        | 12.6 (Window slid forward)

*/