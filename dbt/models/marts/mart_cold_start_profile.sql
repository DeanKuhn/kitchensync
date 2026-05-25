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
        avg(p.avg_hourly_quantity) as avg_hourly_quantity,
        m.category

    from profile p
    inner join menu m on p.item_id = m.item_id

    group by
        category,
        day_of_week,
        sale_hour

)


select * from final


/*

--- DATA TRANSFORMATION VISUALIZATION ---

STEP 1: item_profile (Detailed averages per item)
ITEM_ID | CATEGORY | DAY | HOUR | AVG_QTY
BURGER  | SANDWICH | 1   | 12   | 10.0

STEP 2: final (Category-level averages for "Cold Starts")
CATEGORY | DAY | HOUR | AVG_CATEGORY_QTY
SANDWICH | 1   | 12   | 8.5 (Average of all sandwiches)

*/