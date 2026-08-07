import os
import joblib
import yaml # type:ignore
import pandas as pd
from sqlalchemy import create_engine # type:ignore
from dotenv import load_dotenv # type:ignore

import ml.features as features
from simulator.pos_simulator import HOURS_AVAILABLE
from simulator.weather import COLD_THRESHOLD_F, HOT_THRESHOLD_F

load_dotenv()

ESTABLISHED_DAYS_THRESHOLD = 14
FEATURE_COLS = features.FEATURE_COLS

# This is a static, date-agnostic weekly grid (no calendar date to look up
# real/synthetic weather for), so warm-path predictions use a neutral
# placeholder sitting in the middle of weather.py's neutral band -- the
# temp/precip combo whose ground-truth multiplier was 1.0x (no effect) for
# every category during training, i.e. "an average, weather-neutral day".
NEUTRAL_TEMP_F = (COLD_THRESHOLD_F + HOT_THRESHOLD_F) / 2
NEUTRAL_PRECIP = 0

with open("config/menu.yaml", "r") as f:
    _menu = yaml.safe_load(f)

with open("config/stores.yaml", "r") as f:
    _stores = yaml.safe_load(f)

ITEM_CATEGORIES = {i["id"]: i["category"] for i in _menu["items"]}
STORE_REGIONS = {s["id"]: s["region"] for s in _stores["stores"]}


def get_all_store_items():

    with open("config/stores.yaml", "r") as f:
        stores = yaml.safe_load(f)

    df = pd.DataFrame(_menu["items"]).rename(columns={"id": "item_id"})
    df = df[df["active"]][["item_id", "category", "time_of_day", "added"]]

    store_ids = [s["id"] for s in stores["stores"]]
    df["key"] = 1
    stores_df = pd.DataFrame({"store_id": store_ids, "key": 1})

    grid = stores_df.merge(df, on="key").drop(columns="key")


    # Build full spine: all store × item × slot_index combinations
    slot_df = pd.DataFrame({'slot_index': range(672)})
    full_grid = grid.merge(slot_df, how='cross')

    full_grid['hour'] = (full_grid['slot_index'] % 96) // 4

    full_grid['window_start'] = full_grid['time_of_day'].map(
        lambda t: HOURS_AVAILABLE[t][0]) # type:ignore

    full_grid['window_end'] = full_grid['time_of_day'].map(
        lambda t: HOURS_AVAILABLE[t][1]) # type:ignore

    in_window = (full_grid['hour'] >= full_grid['window_start']) & \
        (full_grid['hour'] < full_grid['window_end'])

    not_yet_added = pd.to_datetime(full_grid['added']).dt.date > \
        pd.Timestamp.now().date()

    full_grid = full_grid[in_window & ~not_yet_added].drop(
        columns=['hour', 'window_start', 'window_end', 'time_of_day', 'added'])

    return full_grid


def get_slot_features():

    engine = create_engine(os.getenv("NEON_DATABASE_URL"))
    query = """
        select
            store_id,
            item_id,
            day_of_week,
            sale_hour,
            (slot_index %% 4) * 15 as sale_minute,
            slot_index,
            avg_slot_quantity,
            sample_size,
            days_observed

        from public.baseline_profile
    """

    df = pd.read_sql(query, engine)
    df["category"] = df["item_id"].map(ITEM_CATEGORIES)

    return df


def get_cold_start_profiles():

    engine = create_engine(os.getenv("NEON_DATABASE_URL"))
    return pd.read_sql("select * from public.cold_start_profile", engine)


def get_traffic_ratio():

    engine = create_engine(os.getenv("NEON_DATABASE_URL"))
    return pd.read_sql("select * from public.traffic_ratio", engine)


def predict(df, df_cold_start, df_ratio, lgbm, store_encoder, item_encoder,
            weather_by_region=None):

    established = df['days_observed'] >= ESTABLISHED_DAYS_THRESHOLD
    in_profile = df['sample_size'] > 0

    print(f"Warm rows: {(established & in_profile).sum()}")
    print(f"Zero rows: {(established & ~in_profile).sum()}")
    print(f"Cold rows: {(~established).sum()}")

    df_warm = df[established & in_profile].copy()
    df_zero = df[established & ~in_profile].copy()
    df_cold = df[~established].copy()

    # Route items unseen during training to cold-start
    known_items = set(item_encoder.classes_)
    unknown_mask = ~df_warm['item_id'].isin(known_items)
    df_cold = pd.concat([df_cold, df_warm[unknown_mask]])
    df_warm = df_warm[~unknown_mask]


    #   --- WARM MODEL ---
    if weather_by_region is not None:
        # Per-date, per-region actual weather (used by the A/B simulation's
        # "perfect forecast" ML side)
        region = df_warm['store_id'].map(STORE_REGIONS)
        df_warm['temp_f'] = region.map(
            lambda r: weather_by_region[r]['temp_f'])
        df_warm['precip'] = region.map(
            lambda r: int(weather_by_region[r]['precip']))
    else:
        df_warm['temp_f'] = NEUTRAL_TEMP_F
        df_warm['precip'] = NEUTRAL_PRECIP

    df_warm['store_id'] = store_encoder.transform(df_warm['store_id'])
    df_warm['item_id'] = item_encoder.transform(df_warm['item_id'])

    df_warm['is_weekend'] = df_warm['day_of_week'].isin([5, 6]).astype(int)

    X = df_warm[FEATURE_COLS]

    df_warm['predicted_units'] = lgbm.predict(X)

    df_warm['store_id'] = store_encoder.inverse_transform(df_warm['store_id'])
    df_warm['item_id'] = item_encoder.inverse_transform(df_warm['item_id'])


    #   --- ZERO MODEL ---
    df_zero['predicted_units'] = 0.0


    #   --- COLD MODEL ---
    # Merge both dataframes on category
    df_cold_start = df_cold_start.rename(columns=
                                    {'avg_slot_quantity': 'category_avg',
                                     'slot_index': 'slot_index'})
    df_cold = df_cold.merge(df_cold_start[['category', 'slot_index', 'category_avg']],
                            on=['category', 'slot_index'])

    # Merge on traffic ratio
    df_cold = df_cold.merge(df_ratio[['store_id', 'traffic_ratio']],
                            on='store_id', how='left')

    # Predict units based on category average and store traffic ratio
    df_cold['predicted_units'] = df_cold['category_avg'] * df_cold['traffic_ratio']

    # Recombine and return
    combined_df = pd.concat([df_warm, df_zero, df_cold])
    assert len(combined_df) == len(df), \
        f"Row count changed in routing: {len(df)} in, {len(combined_df)} out"

    return combined_df[['store_id', 'item_id', 'predicted_units', 'slot_index']]


def generate_production_plan(weather_by_region=None, verbose=True):
    """Builds the full store/item/slot production plan.

    weather_by_region=None (default) uses the static grid's neutral weather
    placeholder -- this is what the live dashboard's public.predictions table
    is built from. Passing a {region: {"temp_f", "precip"}} dict instead
    conditions the warm-path model on that actual per-date weather -- used by
    run_daily_simulation.py's ML side, treating the A/B simulation's
    synthetic ground-truth weather for that date as a "perfect forecast".
    """
    lgbm = joblib.load("ml/models/lgbm.joblib")
    store_encoder = joblib.load("ml/models/store_encoder.joblib")
    item_encoder = joblib.load("ml/models/item_encoder.joblib")

    if verbose: print("Loading items per store...")
    grid = get_all_store_items()

    if verbose: print("Loading current conditions from Neon...")
    df_features = get_slot_features()

    # Left-join profile features onto full spine
    df = grid.merge(df_features, on=["store_id", "item_id", "slot_index"], how="left")

    # Derive time features from slot_index for rows missing from profile
    df['day_of_week'] = df['day_of_week'].fillna(df['slot_index'] // 96).astype(int)
    df['sale_hour']   = df['sale_hour'].fillna((df['slot_index'] % 96) // 4).astype(int)
    df['sale_minute'] = df['sale_minute'].fillna((df['slot_index'] % 4) * 15).astype(int)
    df['avg_slot_quantity'] = df['avg_slot_quantity'].fillna(0)
    df['sample_size'] = df['sample_size'].fillna(0).astype(int)
    df['days_observed'] = df.groupby(['store_id', 'item_id'])['days_observed'].transform('max')
    df['days_observed'] = df['days_observed'].fillna(0).astype(int)

    # Create a new column, category, with no null values
    df['category'] = df['category_y'].fillna(df['category_x'])
    df = df.drop(columns=['category_x', 'category_y'])

    if verbose: print("Loading cold start data from Neon...")
    df_cold_start = get_cold_start_profiles()
    df_ratio = get_traffic_ratio()

    if verbose: print(f"Running inference for {len(df)} store/item combinations...")
    return predict(df, df_cold_start, df_ratio, lgbm, store_encoder, item_encoder,
                   weather_by_region=weather_by_region)


if __name__ == "__main__":

    production_plan = generate_production_plan()

    engine = create_engine(os.getenv("NEON_DATABASE_URL"))

    production_plan['predicted_at'] = pd.Timestamp.now()
    production_plan.to_sql('predictions', engine, schema="public",
                           if_exists='replace', index=False, chunksize=10000)

    print("\n--- PRODUCTION PLAN SUMMARY ---")
    print(f"Total predictions written : {len(production_plan)}")
    print(f"Stores covered            : {production_plan['store_id'].nunique()}")
    print(f"Items covered             : {production_plan['item_id'].nunique()}")
    print(f"Slots covered             : {production_plan['slot_index'].nunique()}")
    print(f"Avg predicted units/slot  : {production_plan['predicted_units'].mean():.2f}")
    print(f"Max predicted units/slot  : {production_plan['predicted_units'].max()}")
    print(f"\nTop 5 items by avg predicted units:")
    top_items = (production_plan.groupby('item_id')['predicted_units']
                 .mean().sort_values(ascending=False).head(5))
    for item, avg in top_items.items(): # type:ignore
        print(f"  {item:<35} {avg:.2f}")