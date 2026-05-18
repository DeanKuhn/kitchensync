with sales as (

    select * from {{ ref('stg_sales_events') }}

),


hourly as (

    select
        store_id,
        item_id,
        sale_date,
        sale_hour,
        sum(quantity) as hourly_quantity

    from sales

    group by
        store_id,
        item_id,
        sale_date,
        sale_hour

),


rolling as (

    select
        store_id,
        item_id,
        sale_date,
        sale_hour,
        hourly_quantity,

        sum(hourly_quantity) over (
            partition by store_id, item_id
            order by sale_date, sale_hour
            rows between 1 preceding and current row
        ) as rolling_1hr,

        sum(hourly_quantity) over (
            partition by store_id, item_id
            order by sale_date, sale_hour
            rows between 4 preceding and current row
        ) as rolling_4hr

    from hourly

)

select * from rolling