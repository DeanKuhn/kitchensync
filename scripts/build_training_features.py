# Neon-native replacement for dbt's mart_ml_training_features model.
# Reuses public.baseline_profile (already the Neon port of
# int_sales__time_of_day_profile, see build_baseline_profile.py) as the
# profile input instead of recomputing it, and joins per-store actual slot
# quantities + public.weather_daily directly in Postgres.
#
# NOT persisted to Neon -- the joined result is ~270MB (vs. a 512MB project
# storage cap) and training is a manual, infrequent event (decision #12), so
# ml/features.py calls build_features() directly and recomputes it in-memory
# each time rather than paying that storage cost permanently.


import yaml # type:ignore
import pandas as pd
from dotenv import load_dotenv # type:ignore

from api.db.connection import get_store_connection, release_connection

load_dotenv()


with open("config/stores.yaml", "r") as f:
    stores = yaml.safe_load(f)


# Ports dbt/models/marts/mart_ml_training_features.sql's spine + final logic.
# store_id/region are trusted internal config (stores.yaml), not user input,
# so they're safely inlined rather than parameterized (also sidesteps
# escaping the literal `%` in the slot_index modulo expression).
def build_query(store_id: str, region: str) -> str:
    return f"""
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

        rolling as (
            select
                item_id,
                sale_date,
                sale_hour,
                day_of_week,
                (day_of_week * 96) + (sale_hour * 4) + slot_bucket as slot_index,
                sum(quantity) as slot_quantity
            from sales
            group by item_id, sale_date, sale_hour, day_of_week, slot_bucket
        ),

        store_dates as (
            select distinct
                sale_date,
                (extract(isodow from sale_date)::int - 1) as day_of_week
            from sales
        ),

        profile as (
            select item_id, day_of_week, sale_hour, slot_index,
                   avg_slot_quantity, sample_size
            from baseline_profile
            where store_id = '{store_id}'
        ),

        spine as (
            select
                p.item_id,
                sd.sale_date,
                p.day_of_week,
                p.sale_hour,
                (p.slot_index % 4) * 15 as sale_minute,
                p.slot_index,
                p.avg_slot_quantity,
                p.sample_size
            from profile p
            inner join store_dates sd
                on sd.day_of_week = p.day_of_week
        )

        select
            s.item_id,
            s.sale_date,
            s.sale_hour,
            s.sale_minute,
            s.slot_index,
            s.day_of_week,
            coalesce(r.slot_quantity, 0) as slot_quantity,
            s.avg_slot_quantity,
            s.sample_size,
            w.temp_f,
            w.precip
        from spine s
        left join rolling r
            on  s.item_id    = r.item_id
            and s.sale_date  = r.sale_date
            and s.slot_index = r.slot_index
        left join weather_daily w
            on  w.region    = '{region}'
            and w.sale_date = s.sale_date
    """


def build_features():

    frames = []

    for store in stores["stores"]:
        store_id = store["id"]
        region = store["region"]
        print(f"[TRAINING FEATURES] Aggregating {store_id}...")

        conn = get_store_connection(store_id)
        df = pd.read_sql(build_query(store_id, region), conn)
        release_connection(conn)

        df.insert(0, "store_id", store_id)
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    # Standalone run is just for manual inspection/sanity-checking the join
    # -- ml/features.py is the real caller, and doesn't persist this either.
    features_df = build_features()
    print(f"[TRAINING FEATURES] Built {len(features_df)} rows (not persisted -- "
          "see module docstring).")
