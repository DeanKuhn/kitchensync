with sales as (

    select * from {{ ref('stg_sales_events') }}

),

totals as (

    select
        store_id,
        sum(quantity) / count(distinct sale_date) as avg_daily_units

    from sales

    group by store_id

),

final as (

    select
        store_id,   -- stores to group by
        avg_daily_units,    -- average daily units per store

        -- store avg_daily units over entire average to get store ratio
        avg_daily_units / (avg(avg_daily_units) over ()) as traffic_ratio

    from totals

)

select * from final