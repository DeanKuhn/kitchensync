# Inference: produces next-hour production plan


import joblib
import yaml # type:ignore
import pandas as pd

from ml.features import get_snowflake_connection, get_snowflake_engine

COLD_START_THRESHOLD = 4


def get_all_store_items(connection):

    # Get all stores
    with open("config/stores.yaml", "r") as f:
        stores = yaml.safe_load(f)

    # Get all active items
    query = """
        select
            item_id,
            category
        from PUBLIC.MENU_ITEMS
        where active = true
    """

    # Create a df of all items
    df = pd.read_sql(query, connection)
    df.columns = df.columns.str.lower()

    # Create a df of all stores
    store_ids = [s["id"] for s in stores["stores"]]
    df["key"] = 1
    stores_df = pd.DataFrame({"store_id": store_ids, "key": 1})

    # Cross-join, creating a grid with all stores and all items
    grid = stores_df.merge(df, on="key").drop(columns="key")

    return grid


def get_current_features(connection):

    query = """
        with latest as (

            select
                sale_date as latest_date,
                sale_hour as latest_hour

            from INTERMEDIATE.INT_SALES__ROLLING_FEATURES
            order by sale_date desc, sale_hour desc
            limit 1

        )

        select
            ms.store_id,
            ms.item_id,
            ms.sale_hour,
            ms.day_of_week,
            ms.rolling_2hr,
            ms.rolling_4hr,
            ms.avg_hourly_quantity,
            ms.sample_size,
            mv.urgency_flag,
            mi.category

        from MARTS.MART_STORE_SALES ms
        inner join MARTS.MART_ITEM_VELOCITY mv
            on ms.store_id = mv.store_id
            and ms.item_id = mv.item_id
        inner join PUBLIC.MENU_ITEMS mi
            on ms.item_id = mi.item_id
        cross join latest l
        where ms.sale_date = l.latest_date
        and ms.sale_hour = l.latest_hour
    """

    df = pd.read_sql(query, connection)
    df.columns = df.columns.str.lower()

    return df


def get_cold_start_profiles(connection):

    query = """
        with latest as (

            select
                day_of_week,
                sale_hour as latest_hour

            from INTERMEDIATE.INT_SALES__ROLLING_FEATURES
            order by sale_date desc, sale_hour desc
            limit 1

        )

        select
            cs.category,
            cs.day_of_week,
            cs.sale_hour,
            cs.avg_hourly_quantity

        from MARTS.MART_COLD_START_PROFILE cs
        cross join latest l
        where cs.day_of_week = l.day_of_week
        and cs.sale_hour = l.latest_hour
    """

    df = pd.read_sql(query, connection)
    df.columns = df.columns.str.lower()

    return df


def predict(df, df_cold_start, lgbm, store_encoder, item_encoder):

    df_warm = df[df['sample_size'] >= COLD_START_THRESHOLD]
    df_cold = df[~df.index.isin(df_warm.index)]


    #   --- WARM MODEL ---

    # Encode store_id and item_id using saved encoders
    df_warm['store_id'] = store_encoder.transform(df_warm['store_id'])
    df_warm['item_id'] = item_encoder.transform(df_warm['item_id'])

    # Build feature matrix in the same column order as training
    FEATURE_COLS = [
        'store_id',
        'item_id',
        'sale_hour',
        'day_of_week',
        'is_weekend',
        'rolling_2hr',
        'rolling_4hr',
        'avg_hourly_quantity',
        'sample_size'
    ]

    df_warm['is_weekend'] = df_warm['day_of_week'].isin([0, 6]).astype(int)

    X = df_warm[FEATURE_COLS]

    # Run inference
    df_warm['predicted_units'] = lgbm.predict(X).round().astype(int)

    # Decode encoded columns
    df_warm['store_id'] = store_encoder.inverse_transform(df_warm['store_id'])
    df_warm['item_id'] = item_encoder.inverse_transform(df_warm['item_id'])


    #   --- COLD MODEL ---

    # Merge both dataframes on category
    df_cold_start = df_cold_start.rename(columns=
                                    {'avg_hourly_quantity': 'category_avg'})
    df_cold = df_cold.merge(df_cold_start[['category', 'category_avg']],
                            on='category')

    df_cold['predicted_units'] = df_cold['category_avg'].round().astype(int)
    df_cold['urgency_flag'] = 'NORMAL'


    # Recombine and return
    combined_df = pd.concat([df_warm, df_cold])

    return combined_df[['store_id', 'item_id', 'predicted_units', 'urgency_flag']]


if __name__ == "__main__":

    connection = get_snowflake_connection()

    # Load models and encoders
    lgbm = joblib.load("ml/models/lgbm.joblib")
    store_encoder = joblib.load("ml/models/store_encoder.joblib")
    item_encoder = joblib.load("ml/models/item_encoder.joblib")

    print("Loading items per store...")
    grid = get_all_store_items(connection)

    print("Loading current conditions from Snowflake...")
    df_features = get_current_features(connection)

    # Combine features and the grid
    df = grid.merge(df_features, on=["store_id", "item_id"], how="left")

    # Create a new column, category, with no null values
    df['category'] = df['category_y'].fillna(df['category_x'])
    df = df.drop(columns=['category_x', 'category_y'])

    print("Loading cold start data from Snowflake...")
    df_cold_start = get_cold_start_profiles(connection)

    connection.close()

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
    production_plan.to_sql('predictions', engine, if_exists='append', index=False)

    print("\n--- PRODUCTION PLAN ---")
    print(production_plan.to_string(index=False))