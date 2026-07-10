# Pulls latest predictions from Snowflake/Postgres


import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import text # type:ignore
from ml.features import get_snowflake_engine
from api.db.connection import get_store_connection, release_connection
import yaml

STORE_TIMEZONE = ZoneInfo("America/Chicago")


# --- MENU CONFIG --
with open("config/menu.yaml") as f:
    menu = yaml.safe_load(f)

category_by_item = {item["id"]: item["category"] for item in menu["items"]}
cost_by_item = {item["id"]: item["cost"] for item in menu["items"]}
hold_time_by_item = {item["id"]: item["hold_time"] for item in menu["items"]}


def get_sim_now(store_id):
    conn = get_store_connection(store_id)
    query = "select max(created_at) from sales_events"
    now_df = pd.read_sql(query, conn)
    release_connection(conn)
    now = now_df.iloc[0, 0]
    return now

def get_today_start(now):
    today_start = now.replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    return today_start


def get_production_plan(store_id, now, today_start):

    # Get Snowflake connection
    sf_engine = get_snowflake_engine()
    neon_engine = get_store_connection(store_id)

    # slot_index day-blocks use 0=Monday..6=Sunday (dayofweekiso - 1 in dbt),
    # matching Python's weekday() -- no conversion needed.
    day_of_week = now.weekday()

    # Calculate slot_index
    slot_index = (day_of_week * 96) + (now.hour * 4) + (now.minute // 15)

    windows = [
        (item_id, (slot_index + offset) % 672)
        for item_id, hold_time in hold_time_by_item.items()
        for offset in range(int(hold_time * 4))
    ]

    windows_df = pd.DataFrame(windows, columns=["item_id", "slot_index"])

    # Join PREDICTIONS with MENU_ITEMS
    query = text("""
        select
            store_id,
            item_id,
            slot_index,
            predicted_units
        from MARTS.PREDICTIONS
        where store_id = :store_id
    """)

    # Return a DataFrame
    predictions_df = pd.read_sql(query, sf_engine, params={"store_id": store_id})

    # Lowercase + add predicted_for column
    predictions_df.columns = predictions_df.columns.str.lower()
    predictions_df = predictions_df.drop(columns=["store_id"])

    # Merge windows and predictions to get the correct windows
    predictions_df = predictions_df.merge(windows_df,
                        on=["item_id", "slot_index"], how="inner")

    # Group by sum
    predictions_df = predictions_df.groupby("item_id")["predicted_units"].sum()
    predictions_df = predictions_df.reset_index()

    # Now query Neon for stockouts
    query = ("""
        select
            item_id,
            sum(quantity_requested) as missed_units
        from stockout_events
        where created_at >= %(today_start)s
        group by item_id
    """)

    df_stockouts = pd.read_sql(query, neon_engine, params={"today_start":
                                                             today_start})

    release_connection(neon_engine)

    # Merge two Data Frames
    df = predictions_df.merge(df_stockouts, on="item_id", how="left")
    df["missed_units"] = df["missed_units"].fillna(0).astype(int)

    df.attrs["predicted_for"] = now
    df["category"] = df["item_id"].map(category_by_item)

    return df


def get_waste_summary(store_id, now, today_start):

    # Get Neon Connection
    engine = get_store_connection(store_id)

    query = ("""
        with today_sales as (
            select
                item_id,
                sum(quantity) as sale_quantity,
                sum(quantity * price) as sale_revenue
            from sales_events
            where created_at >= %(today_start)s
            group by item_id
        ),

        today_waste as (
            select
                item_id,
                sum(quantity) as waste_quantity
            from waste_log
            where created_at >= %(today_start)s
            group by item_id
        ),

        final as (
            select
                coalesce(s.item_id, w.item_id) as item_id,
                coalesce(sale_quantity, 0) as sale_quantity,
                coalesce(sale_revenue, 0) as sale_revenue,
                coalesce(waste_quantity, 0) as waste_quantity
            from today_sales s
            full outer join today_waste w
            on s.item_id = w.item_id
        )

        select * from final
    """)

    # Return a DataFrame with area, category, waste_cost, and sale_revenue
    df = pd.read_sql(query, engine, params={"today_start": today_start})

    release_connection(engine)

    # Add category and waste costs mapped from dictionaries from menu config
    df["category"] = df["item_id"].map(category_by_item)
    df["cost"] = df["item_id"].map(cost_by_item)
    df["waste_cost"] = df["waste_quantity"] * df["cost"]

    return df