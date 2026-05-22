with sales as (

    -- ref() is how other dbt models are referenced
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


profile as (

    select
        store_id,
        item_id,
        day_of_week,
        sale_hour,
        avg(hourly_quantity) as avg_hourly_quantity,

        -- sample_size is the count of how many data points went
        -- into each average
        count(*) as sample_size

    from hourly

    group by
        store_id,
        item_id,
        day_of_week,
        sale_hour

)


select * from profile


-- store_id | item_id | day_of_week | sale_hour | avg_quantity | sample_size
-- ---------+---------+-------------+-----------+--------------+------------
-- store_01 | HOT_DOG | 3           | 12        | 5            | 40