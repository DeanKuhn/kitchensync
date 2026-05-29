# Pulls latest predictions from Snowflake/Postgres


import pandas as pd
from datetime import datetime
from sqlalchemy import text # type:ignore
from ml.features import get_snowflake_engine


def get_production_plan(store_id):

    # 1. Get Snowflake connection
    engine = get_snowflake_engine()

    # 2. Get slot_index
    now = datetime.now()
    slot_index = (now.weekday() * 96) + (now.hour * 4) + (now.minute // 15)

    # 3. Join PREDICTIONS with MART_STOCKOUT_SUMMARY and MENU_ITEMS
    # We use a LEFT JOIN because we want to see the plan even if there are 0 stockouts
    query = text("""
        with menu as (
            select *
            from PUBLIC.MENU_ITEMS
        ),

        current_stockouts as (
            select
                item_id,
                total_missed_units
            from MARTS.MART_STOCKOUT_SUMMARY
            where store_id = :store_id
            and stockout_date = (select max(stockout_date) from MARTS.MART_STOCKOUT_SUMMARY where store_id = :store_id)
            and stockout_hour = (select max(stockout_hour) from MARTS.MART_STOCKOUT_SUMMARY where store_id = :store_id)
        ),

        predictions as (
            select
                store_id,
                item_id,
                slot_index,
                predicted_units
            from MARTS.PREDICTIONS
            where store_id = :store_id
            and slot_index = :slot_index
        )

        select
            p.item_id,
            p.predicted_units,
            m.category,
            coalesce(s.total_missed_units, 0) as missed_units

        from predictions p
        left join current_stockouts s
            on p.item_id = s.item_id
        left join menu m
            on m.item_id = p.item_id
    """)

    # 4. Return a DataFrame
    df = pd.read_sql(query, engine, params={"store_id": store_id,
                                            "slot_index": slot_index})
    df.columns = df.columns.str.lower()

    return df


def get_waste_summary(store_id):

    # 1. Get Snowflake Connection
    engine = get_snowflake_engine()

    # 2. Queries MARTS.MART_WASTE_PERCENTAGE for most recent date
    query = text("""
        select
            category,
            waste_cost,
            sale_quantity,
            sale_revenue

        from MARTS.MART_WASTE_PERCENTAGE
        where waste_date = (select max(waste_date) from
        KS_DB.MARTS.MART_WASTE_PERCENTAGE where store_id = :store_id)
        and store_id = :store_id
    """)

    # 3. Return a DataFrame with area, category, waste_cost, and sale_revenue
    df = pd.read_sql(query, engine, params={"store_id": store_id})

    return df