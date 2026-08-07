# Neon-native replacement for dbt's int_sales__time_of_day_profile model.
# Computes the historical-average baseline profile directly from Neon
# per-store sales_events, so the A/B baseline keeps updating nightly
# without Snowflake/dbt.


import os
import yaml # type:ignore
import pandas as pd
from sqlalchemy import create_engine, text # type:ignore
from dotenv import load_dotenv # type:ignore

from api.db.connection import get_store_connection, release_connection

load_dotenv()


with open("config/stores.yaml", "r") as f:
    stores = yaml.safe_load(f)


# Ports dbt/models/intermediate/int_sales__time_of_day_profile.sql to Postgres:
#   - day_of_week: EXTRACT(ISODOW) - 1 matches Snowflake's DAYOFWEEKISO(created_at) - 1 (0=Monday)
#   - slot_index: (day_of_week * 96) + (sale_hour * 4) + FLOOR(minute / 15)
#   - avg_slot_quantity: SUM(quantity) / total_dates, where total_dates is
#     days observed for that store/day_of_week (not just days with sales for
#     that item) -- preserves the conditional-mean fix from design decision #15
QUERY = """
    with sales as (
        select
            item_id,
            quantity,
            created_at::date as sale_date,
            extract(hour from created_at)::int as sale_hour,
            (extract(isodow from created_at)::int - 1) as day_of_week,
            floor(extract(minute from created_at) / 15)::int as slot_bucket
        from sales_events
    ),

    fifteen_min as (
        select
            item_id,
            sale_date,
            sale_hour,
            day_of_week,
            (day_of_week * 96) + (sale_hour * 4) + slot_bucket as slot_index,
            sum(quantity) as quantity
        from sales
        group by item_id, sale_date, sale_hour, day_of_week, slot_bucket
    ),

    total_days as (
        select day_of_week, count(distinct sale_date) as total_dates
        from sales
        group by day_of_week
    )

    select
        f.item_id,
        f.day_of_week,
        f.sale_hour,
        f.slot_index,
        sum(f.quantity)::float / t.total_dates as avg_slot_quantity,
        count(*) as sample_size
    from fifteen_min f
    join total_days t on f.day_of_week = t.day_of_week
    group by f.item_id, f.sale_hour, f.slot_index, f.day_of_week, t.total_dates
"""

# Kept as a separate, lightweight query rather than a 3rd CTE joined into
# QUERY above -- adding it as a join inside QUERY pushed Postgres into a
# heavier hash-join plan that exceeded Neon's compute memory limit on the
# full 70-day/12-store dataset. This one's cheap (single group by, no
# cross-join blowup) and gets merged into the profile in pandas instead.
DAYS_OBSERVED_QUERY = """
    select item_id, count(distinct created_at::date) as days_observed
    from sales_events
    group by item_id
"""


def build_profile():

    frames = []

    for store in stores["stores"]:
        store_id = store["id"]
        print(f"[BASELINE] Aggregating {store_id}...")

        conn = get_store_connection(store_id)
        df = pd.read_sql(QUERY, conn)
        days_observed = pd.read_sql(DAYS_OBSERVED_QUERY, conn)
        release_connection(conn)

        df = df.merge(days_observed, on="item_id", how="left")
        df.insert(0, "store_id", store_id)
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


def write_profile(df):
    engine = create_engine(os.getenv("NEON_DATABASE_URL"))

    with engine.begin() as conn:
        conn.execute(text("SET search_path TO public;"))
        df.to_sql("baseline_profile", conn, schema="public",
                   if_exists="replace", index=False, chunksize=10000)

    print(f"[BASELINE] Wrote {len(df)} rows to public.baseline_profile.")


if __name__ == "__main__":
    profile_df = build_profile()
    write_profile(profile_df)