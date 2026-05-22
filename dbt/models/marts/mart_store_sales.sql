with rolling as (

    select * from {{ ref('int_sales__rolling_features') }}

),


-- store_id | item_id | ... | hourly_quantity | rolling_2hr | rolling_4hr
-- ---------+---------+-----+-----------------+-------------+------------
-- store_01 | HOT_DOG | ... | 12              | 18          | 40


profile as (

    select * from {{ ref('int_sales__time_of_day_profile') }}

),


-- store_id | item_id | day_of_week | sale_hour | avg_hourly_quantity | sample_size
-- ---------+---------+-------------+-----------+---------------------+------------
-- store_01 | HOT_DOG | 3           | 12        | 10                  | 40


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


-- ... | hourly_quantity | rolling_2hr | rolling_4hr | avg_hourly_quantity | sample_size
-- ----+-----------------+-------------+-------------+---------------------+------------
--     | 12              | 18          | 40          | 10                  | 40