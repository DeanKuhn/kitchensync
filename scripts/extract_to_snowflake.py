# One time and on demand extract from Neon to Snowflake
# Pulls all sales_events from each store schema in Neon and loads tham into a
# single RAW.SALES_EVENTS table in Snowflake with store_id added
#
# This is a full reload; RAW.SALES_EVENTS is truncated on every run


import os
import yaml # type:ignore
import pandas as pd
import snowflake.connector # type:ignore
from snowflake.connector.pandas_tools import write_pandas # type:ignore
from dotenv import load_dotenv # type:ignore

from api.db.connection import get_store_connection, release_connection

load_dotenv()


with open("config/stores.yaml", "r") as f:
    stores = yaml.safe_load(f)


def get_snowflake_connection():
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        role=os.getenv("SNOWFLAKE_ROLE"),
        schema="RAW"
    )


def ensure_raw_table(sf_cursor):
    sf_cursor.execute("""
        CREATE TABLE IF NOT EXISTS RAW.SALES_EVENTS (
            store_id VARCHAR,
            item_id VARCHAR,
            quantity INTEGER,
            price FLOAT,
            created_at TIMESTAMP
        )
    """)


def extract():

    print("Connecting to Snowflake...")
    sf_conn = get_snowflake_connection()
    sf_cursor = sf_conn.cursor()

    ensure_raw_table(sf_cursor)

    print("Truncating RAW.SALES_EVENTS...")
    sf_cursor.execute("TRUNCATE TABLE RAW.SALES_EVENTS")

    for store in stores["stores"]:

        store_id = store["id"]

        print(f"[{store_id}] Extracting from Neon...")
        neon_conn = get_store_connection(store_id)
        neon_cursor = neon_conn.cursor()

        neon_cursor.execute("""
            SELECT item_id, quantity, price, created_at
            FROM sales_events
        """)

        rows = neon_cursor.fetchall()

        neon_cursor.close()
        release_connection(neon_conn)

        if not rows:
            print(f"[{store_id}] No rows found, skipping.")
            continue

        # Build a dataframe with store_id added
        df = pd.DataFrame(rows,
            columns=["item_id", "quantity", "price", "created_at"])

        df.insert(0, "store_id", store_id)
        df = df.dropna(subset=["created_at"])

        # Ensure created_at is formatted as a string Snowflake can parse
        df["created_at"] = \
            pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")

        # Snowflake expects uppercase column names
        df.columns = [c.upper() for c in df.columns]

        success, chunks, rows_loaded, output = write_pandas(
            sf_conn,
            df,
            "SALES_EVENTS",
            schema="RAW",
            database="KS_DB"
        )

        if success:
            print(f"[{store_id}] Loaded {rows_loaded} rows into Snowflake.")
        else:
            print(f"[{store_id}] Load failed: {output}")

    sf_cursor.close()
    sf_conn.close()
    print("Extract complete.")


if __name__ == "__main__":
    extract()