with profile as (

    select * from {{ ref('int_sales__time_of_day_profile') }}

),


-- store_id | item_id | day_of_week | sale_hour | avg_hourly_quantity | sample_size
-- ---------+---------+-------------+-----------+---------------------+------------
-- store_01 | HOT_DOG | 3           | 12        | 10                  | 40


menu as (

    select * from {{ ref('menu_items') }}

),


-- item_id      | name         | area     | category | active | added
-- -------------+--------------+----------+----------+--------+-----------
-- CHEESEBURGER | Cheeseburger | hot_spot | all_day  | true   | 2024-01-01


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


-- category | day_of_week | sale_hour | avg_hourly_quantity
-- ---------+-------------+-----------+--------------------
-- all_day  | 5           | 11        | 9