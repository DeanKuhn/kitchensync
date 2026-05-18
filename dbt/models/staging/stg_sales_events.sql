with source as (

    -- First get the source using Jinja formatting
    select * from {{ source('raw', 'sales_events') }}

),


cleaned as (

    select
        store_id,
        item_id,
        quantity::integer       as quantity,
        price::float            as price,
        created_at::timestamp   as created_at,
        created_at::date        as sale_date,
        -- HOUR and DAYOFWEEK are Snowflake commands, same as
        -- datetime.hour and datetime.weekday
        hour(created_at)        as sale_hour,
        dayofweek(created_at)   as day_of_week

    from source

    -- Double check to ensure no null columns
    where created_at is not null

)


-- dbt needs this \/
select * from cleaned


-- To run:
--  1. Activate venv (source .venv/bin/activate)
--  2. Go into dbt folder (cd dbt)
--  3. Use uv to run the dbt command:
--     uv run dbt run --select stg_sales_events