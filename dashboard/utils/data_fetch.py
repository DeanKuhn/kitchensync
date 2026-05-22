# Pulls latest predictions from Snowflake/Postgres


import pandas as pd
from ml.features import get_snowflake_engine


def get_production_plan(store_id):

    # 1. Get Snowflake connection
    engine = get_snowflake_engine()

    # 2. Queries MARTS.PREDICTIONS for latest predicted_at timestamp, filtered
    # to the given store id
    query = f"""
        select
            store_id,
            item_id,
            predicted_units,
            urgency_flag,
            predicted_at

        from MARTS.PREDICTIONS
        where predicted_at = (select max(predicted_at) from MARTS.PREDICTIONS)
        and store_id = '{store_id}'
    """

    # 3. Return a DataFrame with just item_id, predicted_units, urgency_flag
    df = pd.read_sql(query, engine)
    df = df.drop(columns=['store_id', 'predicted_at'])

    return df