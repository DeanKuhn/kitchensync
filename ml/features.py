# Feature engineering from mart/intermediate models


import os
import pandas as pd
import snowflake.connector # type:ignore
from sqlalchemy import create_engine # type:ignore
from dotenv import load_dotenv # type:ignore
from urllib.parse import quote_plus

load_dotenv()


FEATURE_COLS = [
    'store_id',
    'item_id',
    'sale_hour',
    'sale_minute',
    'slot_index',
    'day_of_week',
    'is_weekend',
    'avg_slot_quantity',
    'sample_size'
]


def get_snowflake_engine(schema="MARTS"):
    account=os.getenv("SNOWFLAKE_ACCOUNT")
    user=os.getenv("SNOWFLAKE_USER")
    password=quote_plus(os.getenv("SNOWFLAKE_PASSWORD"))
    database=os.getenv("SNOWFLAKE_DATABASE")
    warehouse=os.getenv("SNOWFLAKE_WAREHOUSE")
    role=os.getenv("SNOWFLAKE_ROLE")

    connection_string = (
        f"snowflake://{user}:{password}@{account}/{database}/{schema}"
        f"?warehouse={warehouse}&role={role}"
    )

    return create_engine(connection_string)


def load_features():

    engine = get_snowflake_engine()

    query = """
        select
            store_id,
            item_id,
            sale_date,
            sale_hour,
            sale_minute,
            slot_index,
            slot_quantity,
            day_of_week,
            avg_slot_quantity,
            sample_size

        from MARTS.MART_STORE_SALES_15MIN
        where sample_size >= 4
    """

    df = pd.read_sql(query, engine)

    # Make columns lowercase so they're easier to work with
    df.columns = df.columns.str.lower()

    # Adds new column: 1 if Saturday or Sunday, 0 else
    df['is_weekend'] = df['day_of_week'].isin([0, 6]).astype(int)


    return df