# Pulls latest predictions from Snowflake/Postgres


import pandas as pd
from sqlalchemy import text # type:ignore
from ml.features import get_snowflake_engine


def get_production_plan(store_id):

    # 1. Get Snowflake connection
    engine = get_snowflake_engine()

    # 2. Join PREDICTIONS with MART_STOCKOUT_SUMMARY
    # We use a LEFT JOIN because we want to see the plan even if there are 0 stockouts
    query = text("""
        with latest_preds as (
            select *
            from MARTS.PREDICTIONS
            where predicted_at = (select max(predicted_at) from MARTS.PREDICTIONS)
            and store_id = :store_id
        ),

        current_stockouts as (
            -- We get the missed units for ONLY the most recent hour recorded
            select
                item_id,
                total_missed_units
            from MARTS.MART_STOCKOUT_SUMMARY
            where store_id = :store_id
            and stockout_date = (select max(stockout_date) from MARTS.MART_STOCKOUT_SUMMARY where store_id = :store_id)
            and stockout_hour = (select max(stockout_hour) from MARTS.MART_STOCKOUT_SUMMARY where store_id = :store_id)
        )

        select
            p.item_id,
            p.predicted_units,
            p.urgency_flag,
            coalesce(s.total_missed_units, 0) as missed_units

        from latest_preds p
        left join current_stockouts s
            on p.item_id = s.item_id
    """)

    # 3. Return a DataFrame
    df = pd.read_sql(query, engine, params={"store_id": store_id})
    df.columns = df.columns.str.lower()

    return df


def get_waste_summary(store_id):

    # 1. Get Snowflake Connection
    engine = get_snowflake_engine()

    # 2. Queries MARTS.MART_WASTE_PERCENTAGE for most recent date
    query = text("""
        select
            area,
            category,
            waste_cost,
            sale_revenue

        from MARTS.MART_WASTE_PERCENTAGE
        where waste_date = (select max(waste_date) from
        KS_DB.MARTS.MART_WASTE_PERCENTAGE where store_id = :store_id)
        and store_id = :store_id
    """)

    # 3. Return a DataFrame with area, category, waste_cost, and sale_revenue
    df = pd.read_sql(query, engine, params={"store_id": store_id})

    return df