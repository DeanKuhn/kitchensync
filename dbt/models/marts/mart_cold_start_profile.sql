with profile as (

    select * from {{ ref('int_sales__time_of_day_profile') }}

),


menu as (

    select * from {{ ref('menu_items') }}

),


final as (

    select
        p.day_of_week,
        p.sale_hour,
        p.sale_minute,
        p.slot_index,
        avg(p.avg_slot_quantity) as avg_slot_quantity,
        m.category

    from profile p
    inner join menu m on p.item_id = m.item_id

    group by
        category,
        day_of_week,
        sale_hour,
        sale_minute,
        slot_index

)


select * from final


/*

--- DATA TRANSFORMATION VISUALIZATION ---

STEP 1: item_profile (Detailed averages per item)
ITEM_ID | DAY_OF_WEEK | HOUR | MINUTE | AVG_SLOT_QUANTITY
BURGER  | 1 (Mon)     | 12   | 0      | 2.8

STEP 2: final (Category-level averages for "Cold Starts")
CATEGORY | DAY | HOUR | AVG_CATEGORY_QTY
SANDWICH | 1   | 12   | 8.5 (Average of all sandwiches)

*/