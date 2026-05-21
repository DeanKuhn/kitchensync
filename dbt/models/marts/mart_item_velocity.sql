with latest_hour as (

    select
        max(sale_date) as latest_date,
        max(sale_hour) as latest_hour

    from {{ ref('int_sales__rolling_features') }}

),


--                               \/ SELECT THESE \/
-- | store_id | item_id | ... | sale_date | sale_hour |
-- | store_01 | hot_dog | ... | 09/09/21  | 13        |


current_sales as (

    select
        r.store_id,
        r.item_id,
        r.sale_date,
        r.sale_hour,
        r.day_of_week,
        r.rolling_2hr

    from {{ ref('int_sales__rolling_features') }} r
    cross join latest_hour lh
    where r.sale_date = lh.latest_date
    and r.sale_hour = lh.latest_hour
),


-- Then, select the rest of the row that matches with the most recent
-- date and hour


profile as (

    select * from {{ ref('int_sales__time_of_day_profile') }}

),


final as (

    select
        cs.store_id,
        cs.item_id,
        cs.sale_date,
        cs.sale_hour,
        cs.rolling_2hr as current_units,
        p.avg_quantity as baseline_units,
        cs.rolling_2hr / nullif(p.avg_quantity, 0) as velocity_ratio,
        case
            when cs.rolling_2hr / nullif(p.avg_quantity, 0) >= 1.4
            then 'URGENT' else 'NORMAL'
        end as urgency_flag

        from current_sales cs
        left join profile p
            on cs.store_id = p.store_id
            and cs.item_id = p.item_id
            and cs.day_of_week = p.day_of_week
            and cs.sale_hour = p.sale_hour

)


select * from final


-- ... | current_units | baseline_units | velocity_ratio | urgency_flag
-- ----+---------------+----------------+----------------+-------------
--     | 18            | 12             | 1.5            | URGENT