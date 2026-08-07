# Neon-native replacement for dbt's mart_store_traffic_ratio model.
# Each store's average daily units relative to the cross-store average --
# used by ml/predict.py to scale the category-level cold-start fallback to
# a given store's traffic level.


import os
import yaml # type:ignore
import pandas as pd
from sqlalchemy import create_engine, text # type:ignore
from dotenv import load_dotenv # type:ignore

from api.db.connection import get_store_connection, release_connection

load_dotenv()


with open("config/stores.yaml", "r") as f:
    stores = yaml.safe_load(f)


QUERY = """
    select
        sum(quantity)::float / count(distinct created_at::date) as avg_daily_units
    from sales_events
"""


def build_traffic_ratio():

    rows = []

    for store in stores["stores"]:
        store_id = store["id"]
        print(f"[TRAFFIC RATIO] Aggregating {store_id}...")

        conn = get_store_connection(store_id)
        df = pd.read_sql(QUERY, conn)
        release_connection(conn)

        rows.append({"store_id": store_id,
                      "avg_daily_units": df["avg_daily_units"].iloc[0]})

    df = pd.DataFrame(rows)
    df["traffic_ratio"] = df["avg_daily_units"] / df["avg_daily_units"].mean()

    return df


def write_ratio(df):
    engine = create_engine(os.getenv("NEON_DATABASE_URL"))

    with engine.begin() as conn:
        conn.execute(text("SET search_path TO public;"))
        df.to_sql("traffic_ratio", conn, schema="public",
                   if_exists="replace", index=False)

    print(f"[TRAFFIC RATIO] Wrote {len(df)} rows to public.traffic_ratio.")


if __name__ == "__main__":
    ratio_df = build_traffic_ratio()
    write_ratio(ratio_df)
