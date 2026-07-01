# Pulls latest predictions from Snowflake/Postgres


import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text # type:ignore
from ml.features import get_snowflake_engine

STORE_TIMEZONE = ZoneInfo("America/Chicago")


def get_production_plan(store_id):

    # 1. Get Snowflake connection
    engine = get_snowflake_engine()

    # 2. Get slot_index
    # datetime.now() is UTC on hosted runners (e.g. Streamlit Community
    # Cloud), which doesn't match store local time, so convert explicitly.
    now = datetime.now(STORE_TIMEZONE)
    # Snowflake's day_of_week (EXTRACT(DAYOFWEEK ...)) is Sunday=0..Saturday=6,
    # while Python's weekday() is Monday=0..Sunday=6 -- convert to match.
    day_of_week = (now.weekday() + 1) % 7
    slot_index = (day_of_week * 96) + (now.hour * 4) + (now.minute // 15)

    # 3. Join PREDICTIONS with MART_STOCKOUT_SUMMARY and MENU_ITEMS
    # We use a LEFT JOIN because we want to see the plan even if there are 0 stockouts
    # Live data has stopped flowing (Neon down), so MART_STOCKOUT_SUMMARY is a
    # frozen historical snapshot -- match today's day-of-week/hour instead of
    # just the latest date, so the numbers stay representative of "now".
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
            and stockout_date = (
                select max(stockout_date) from MARTS.MART_STOCKOUT_SUMMARY
                where store_id = :store_id
                and extract(dayofweek from stockout_date) = :day_of_week
            )
            and stockout_hour = (
                select max(stockout_hour) from MARTS.MART_STOCKOUT_SUMMARY
                where store_id = :store_id
                and extract(dayofweek from stockout_date) = :day_of_week
                and stockout_hour <= :hour
            )
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
                                            "slot_index": slot_index,
                                            "day_of_week": day_of_week,
                                            "hour": now.hour})
    df.columns = df.columns.str.lower()
    df.attrs["predicted_for"] = now

    return df


def get_waste_summary(store_id):

    # 1. Get Snowflake Connection
    engine = get_snowflake_engine()

    # 2. Queries MARTS.MART_WASTE_PERCENTAGE for the most recent date matching
    # today's day-of-week (data is a frozen historical snapshot while Neon is
    # down, so this keeps the numbers representative of "now" rather than
    # whichever day happened to be extracted last)
    now = datetime.now(STORE_TIMEZONE)
    day_of_week = (now.weekday() + 1) % 7

    query = text("""
        select
            category,
            waste_cost,
            sale_quantity,
            sale_revenue

        from MARTS.MART_WASTE_PERCENTAGE
        where store_id = :store_id
        and waste_date = (
            select max(waste_date) from KS_DB.MARTS.MART_WASTE_PERCENTAGE
            where store_id = :store_id
            and extract(dayofweek from waste_date) = :day_of_week
        )
    """)

    # 3. Return a DataFrame with area, category, waste_cost, and sale_revenue
    df = pd.read_sql(query, engine, params={"store_id": store_id,
                                            "day_of_week": day_of_week})

    return df