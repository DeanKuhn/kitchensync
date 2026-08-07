# Neon-native replacement for dbt's mart_cold_start_profile model.
# Category-level average demand by (day_of_week, sale_hour, slot_index) --
# fallback for items with fewer than ESTABLISHED_DAYS_THRESHOLD days of
# history (see ml/predict.py). Averages public.baseline_profile's per-item
# avg_slot_quantity across every item sharing a category, dropping store_id
# (cold start is a global fallback; ml/predict.py scales it per store via
# public.traffic_ratio separately).


import os
import yaml # type:ignore
import pandas as pd
from sqlalchemy import create_engine, text # type:ignore
from dotenv import load_dotenv # type:ignore

load_dotenv()


with open("config/menu.yaml", "r") as f:
    menu = yaml.safe_load(f)

item_categories = {i["id"]: i["category"] for i in menu["items"]}


def build_cold_start_profile():
    engine = create_engine(os.getenv("NEON_DATABASE_URL"))

    df = pd.read_sql("""
        select item_id, day_of_week, sale_hour, slot_index, avg_slot_quantity
        from public.baseline_profile
    """, engine)

    df["category"] = df["item_id"].map(item_categories)
    df = df.dropna(subset=["category"])

    profile = (
        df.groupby(["category", "day_of_week", "sale_hour", "slot_index"])
          ["avg_slot_quantity"].mean()
          .reset_index()
    )

    return profile


def write_profile(df):
    engine = create_engine(os.getenv("NEON_DATABASE_URL"))

    with engine.begin() as conn:
        conn.execute(text("SET search_path TO public;"))
        df.to_sql("cold_start_profile", conn, schema="public",
                   if_exists="replace", index=False, chunksize=10000)

    print(f"[COLD START] Wrote {len(df)} rows to public.cold_start_profile.")


if __name__ == "__main__":
    profile_df = build_cold_start_profile()
    write_profile(profile_df)
