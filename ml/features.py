# Feature engineering from mart/intermediate models


import os
import pandas as pd
import snowflake.connector # type:ignore
from sqlalchemy import create_engine # type:ignore
from cryptography.hazmat.primitives.serialization import load_pem_private_key # type:ignore
from dotenv import load_dotenv # type:ignore


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
    key_pem = os.getenv("SNOWFLAKE_PRIVATE_KEY")
    if key_pem:
        # Cloud deployments (e.g. Streamlit Community Cloud) have no
        # filesystem to mount a key file into, so the PEM contents are
        # passed directly via a secret/env var instead.
        key_bytes = key_pem.encode()
    else:
        key_path = os.path.expanduser(os.getenv("SNOWFLAKE_PRIVATE_KEY_PATH", "~/.ssh/snowflake_rsa.p8"))
        with open(key_path, "rb") as f:
            key_bytes = f.read()
    private_key = load_pem_private_key(key_bytes, password=None)
    account=os.getenv("SNOWFLAKE_ACCOUNT")
    user=os.getenv("SNOWFLAKE_USER")
    database=os.getenv("SNOWFLAKE_DATABASE")
    warehouse=os.getenv("SNOWFLAKE_WAREHOUSE")
    role=os.getenv("SNOWFLAKE_ROLE")

    connection_string = (
        f"snowflake://{user}@{account}/{database}/{schema}"
        f"?warehouse={warehouse}"
        f"&role={role}"
    )

    return create_engine(connection_string,
        connect_args = {"private_key": private_key})


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

        from MARTS.MART_ML_TRAINING_FEATURES
    """

    df = pd.read_sql(query, engine)

    # Make columns lowercase so they're easier to work with
    df.columns = df.columns.str.lower()

    # Adds new column: 1 if Saturday or Sunday, 0 else
    df['is_weekend'] = df['day_of_week'].isin([0, 6]).astype(int)


    return df