# Inference: produces next-hour production plan


import joblib
import yaml # type:ignore
import pandas as pd

from ml.features import get_snowflake_engine
import ml.features as features
from simulator.pos_simulator import HOURS_AVAILABLE

COLD_START_THRESHOLD = 4
FEATURE_COLS = features.FEATURE_COLS


def get_all_store_items():

    # Get all stores
    with open("config/stores.yaml", "r") as f:
        stores = yaml.safe_load(f)

    # Get all active items
    engine = get_snowflake_engine()
    query = """
        select
            item_id,
            category,
            time_of_day,
            added
        from PUBLIC.MENU_ITEMS
        where active = true
    """

    # Create a df of all items
    df = pd.read_sql(query, engine)
    df.columns = df.columns.str.lower()

    # Create a df of all stores
    store_ids = [s["id"] for s in stores["stores"]]
    df["key"] = 1
    stores_df = pd.DataFrame({"store_id": store_ids, "key": 1})

    # Cross-join, creating a grid with all stores and all items
    grid = stores_df.merge(df, on="key").drop(columns="key")

    return grid


def get_slot_features():

    engine = get_snowflake_engine()
    query = """
        select
            p.store_id,
            p.item_id,
            p.day_of_week,
            p.sale_hour,
            (p.slot_index % 4) * 15 as sale_minute,
            p.slot_index,
            p.avg_slot_quantity,
            p.sample_size,
            m.category

        from INTERMEDIATE.INT_SALES__TIME_OF_DAY_PROFILE p
        inner join PUBLIC.MENU_ITEMS m
            on p.item_id = m.item_id
    """

    df = pd.read_sql(query, engine)
    df.columns = df.columns.str.lower()

    return df


def get_cold_start_profiles():

    engine = get_snowflake_engine()
    query = "select * from MARTS.MART_COLD_START_PROFILE"

    df = pd.read_sql(query, engine)
    df.columns = df.columns.str.lower()

    return df


def predict(df, df_cold_start, lgbm, store_encoder, item_encoder):

    df_warm = df[df['sample_size'] >= COLD_START_THRESHOLD]
    df_cold = df[~df.index.isin(df_warm.index)]

    # Route items unseen during training to cold-start
    known_items = set(item_encoder.classes_)
    unknown_mask = ~df_warm['item_id'].isin(known_items)
    df_cold = pd.concat([df_cold, df_warm[unknown_mask]])
    df_warm = df_warm[~unknown_mask]


    #   --- WARM MODEL ---

    # Encode store_id and item_id using saved encoders
    df_warm['store_id'] = store_encoder.transform(df_warm['store_id'])
    df_warm['item_id'] = item_encoder.transform(df_warm['item_id'])

    df_warm['is_weekend'] = df_warm['day_of_week'].isin([0, 6]).astype(int)

    X = df_warm[FEATURE_COLS]

    # Run inference
    df_warm['predicted_units'] = lgbm.predict(X)

    # Decode encoded columns
    df_warm['store_id'] = store_encoder.inverse_transform(df_warm['store_id'])
    df_warm['item_id'] = item_encoder.inverse_transform(df_warm['item_id'])


    #   --- COLD MODEL ---

    # Merge both dataframes on category
    df_cold_start = df_cold_start.rename(columns=
                                    {'avg_slot_quantity': 'category_avg',
                                     'slot_index': 'slot_index'})
    df_cold = df_cold.merge(df_cold_start[['category', 'slot_index', 'category_avg']],
                            on=['category', 'slot_index'])

    df_cold['predicted_units'] = df_cold['category_avg']


    # Recombine and return
    combined_df = pd.concat([df_warm, df_cold])

    return combined_df[['store_id', 'item_id', 'predicted_units', 'slot_index']]


if __name__ == "__main__":

    # Load models and encoders
    lgbm = joblib.load("ml/models/lgbm.joblib")
    store_encoder = joblib.load("ml/models/store_encoder.joblib")
    item_encoder = joblib.load("ml/models/item_encoder.joblib")

    print("Loading items per store...")
    grid = get_all_store_items()

    print("Loading current conditions from Snowflake...")
    df_features = get_slot_features()

    # Build full spine: all store × item × slot_index combinations
    slot_df = pd.DataFrame({'slot_index': range(672)})
    full_grid = grid.merge(slot_df, how='cross')

    # Drop slot/item combos outside the item's time_of_day window (and items
    # not yet added) - these can never have real sales, so leaving them in
    # lets the cold-start category average leak nonzero values from other
    # items in the same category with a different window (see decision #18).

    full_grid['hour'] = (full_grid['slot_index'] % 96) // 4

    full_grid['window_start'] = full_grid['time_of_day'].map(
        lambda t: HOURS_AVAILABLE[t][0])

    full_grid['window_end'] = full_grid['time_of_day'].map(
        lambda t: HOURS_AVAILABLE[t][1])

    in_window = (full_grid['hour'] >= full_grid['window_start']) & \
        (full_grid['hour'] < full_grid['window_end'])

    not_yet_added = pd.to_datetime(full_grid['added']).dt.date > \
        pd.Timestamp.now().date()

    full_grid = full_grid[in_window & ~not_yet_added].drop(
        columns=['hour', 'window_start', 'window_end', 'time_of_day', 'added'])

    # Left-join profile features onto full spine
    df = full_grid.merge(df_features, on=["store_id", "item_id", "slot_index"], how="left")

    # Derive time features from slot_index for rows missing from profile
    df['day_of_week'] = df['day_of_week'].fillna(df['slot_index'] // 96).astype(int)
    df['sale_hour']   = df['sale_hour'].fillna((df['slot_index'] % 96) // 4).astype(int)
    df['sale_minute'] = df['sale_minute'].fillna((df['slot_index'] % 4) * 15).astype(int)
    df['avg_slot_quantity'] = df['avg_slot_quantity'].fillna(0)
    df['sample_size'] = df['sample_size'].fillna(0)

    # Create a new column, category, with no null values
    df['category'] = df['category_y'].fillna(df['category_x'])
    df = df.drop(columns=['category_x', 'category_y'])

    print("Loading cold start data from Snowflake...")
    df_cold_start = get_cold_start_profiles()


    print(f"Warm rows: {len(df[df['sample_size'] >= COLD_START_THRESHOLD])}")
    print(f"Cold rows: {len(df[df['sample_size'] < COLD_START_THRESHOLD])}")
    print(f"NULL category rows: {df['category'].isna().sum()}")

    print(f"Running inference for {len(df)} store/item combinations...")
    production_plan = \
        predict(df, df_cold_start, lgbm, store_encoder, item_encoder)

    # Get Snowflake engine created in features.py
    engine = get_snowflake_engine()

    # Add timestamp, and make sure to append so previous predictions can be
    # observed and learned from
    production_plan['predicted_at'] = pd.Timestamp.now()
    production_plan.to_sql('predictions', engine, if_exists='replace', index=False, chunksize=10000)

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
    for item, avg in top_items.items():
        print(f"  {item:<35} {avg:.2f}")