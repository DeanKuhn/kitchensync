# Pulls latest predictions from Snowflake/Postgres


import pandas as pd
from sqlalchemy import text # type:ignore
from ml.features import get_snowflake_engine


def get_production_plan(store_id):

    # 1. Get Snowflake connection
    engine = get_snowflake_engine()

    # 2. Queries MARTS.PREDICTIONS for latest predicted_at timestamp, filtered
    # to the given store id
    query = text("""
        select
            store_id,
            item_id,
            predicted_units,
            urgency_flag,
            predicted_at

        from MARTS.PREDICTIONS
        where predicted_at = (select max(predicted_at) from MARTS.PREDICTIONS)
        and store_id = :store_id
    """)

    # 3. Return a DataFrame with just item_id, predicted_units, urgency_flag
    df = pd.read_sql(query, engine, params={"store_id": store_id})
    df.columns = df.columns.str.lower()
    df = df.drop(columns=['store_id', 'predicted_at'])

    return df


def get_waste_summary(store_id):

    # 1. Get Snowflake Connection
    engine = get_snowflake_engine()

    # 2. Queries MARTS.MART_WASTE_PERCENTAGE for most recent date
    query = text("""
        select
            area,
            category,
            waste_cost,
            sale_revenue

        from MARTS.MART_WASTE_PERCENTAGE
        where waste_date = (select max(waste_date) from
        KS_DB.MARTS.MART_WASTE_PERCENTAGE where store_id = :store_id)
        and store_id = :store_id
    """)

    # 3. Return a DataFrame with area, category, waste_cost, and sale_revenue
    df = pd.read_sql(query, engine, params={"store_id": store_id})
    print(df.columns.tolist())

    return df