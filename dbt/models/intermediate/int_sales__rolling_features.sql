with sales as (

    select * from {{ ref('stg_sales_events') }}

),


hourly as (

    select
        store_id,
        item_id,
        sale_date,
        sale_hour,
        day_of_week,
        sum(quantity) as hourly_quantity

    from sales

    group by
        store_id,
        item_id,
        sale_date,
        sale_hour,
        day_of_week

),


-- store_id | item_id | ... | hourly_quantity
-- ---------+---------+-----+----------------
-- store_01 | HOT_DOG | ... | 12


rolling as (

    select
        store_id,
        item_id,
        sale_date,
        sale_hour,
        day_of_week,
        hourly_quantity,

        sum(hourly_quantity) over (
            partition by store_id, item_id
            order by sale_date, sale_hour
            rows between 1 preceding and current row
        ) as rolling_2hr,

        sum(hourly_quantity) over (
            partition by store_id, item_id
            order by sale_date, sale_hour
            rows between 3 preceding and current row
        ) as rolling_4hr

    from hourly

)


select * from rolling


-- store_id | item_id | ... | hourly_quantity | rolling_2hr | rolling_4hr
-- ---------+---------+-----+-----------------+-------------+------------
-- store_01 | HOT_DOG | ... | 12              | 12          | 40