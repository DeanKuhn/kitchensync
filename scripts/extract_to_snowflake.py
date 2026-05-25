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


def ensure_waste_table(sf_cursor):
    sf_cursor.execute("""
        CREATE TABLE IF NOT EXISTS RAW.WASTE_LOG (
            store_id VARCHAR,
            item_id VARCHAR,
            quantity INTEGER,
            created_at TIMESTAMP)
    """)


def ensure_stockout_table(sf_cursor):
    sf_cursor.execute("""
        CREATE TABLE IF NOT EXISTS RAW.STOCKOUT_EVENTS (
            store_id VARCHAR,
            item_id VARCHAR,
            quantity_requested INTEGER,
            created_at TIMESTAMP)
    """)


def extract(sf_conn, sf_cursor, neon_table, sf_table, columns):

    for store in stores["stores"]:

        store_id = store["id"]

        # Find most recent sales created_at per store, save it as
        # sales_watermarks
        sf_cursor.execute(f"""
            SELECT MAX(created_at) FROM RAW.{sf_table}
            WHERE store_id = %s
        """, (store_id,))

        watermark = sf_cursor.fetchone()[0]

        print(f"[{store_id}] Extracting from Neon...")
        neon_conn = get_store_connection(store_id)
        neon_cursor = neon_conn.cursor()

        if watermark:
            neon_cursor.execute(f"""
                SELECT {','.join(columns)}
                FROM {neon_table}
                WHERE created_at > %s
            """, (watermark,))
        else:
            neon_cursor.execute(f"""
                SELECT {','.join(columns)}
                FROM {neon_table}
            """)

        rows = neon_cursor.fetchall()

        neon_cursor.close()
        release_connection(neon_conn)

        if rows:
            # Build a dataframe with store_id added
            df = pd.DataFrame(rows,
                columns=columns)

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
                sf_table,
                schema="RAW",
                database="KS_DB"
            )

            if success:
                print(f"[{store_id}] Loaded {rows_loaded} rows into Snowflake.")
            else:
                print(f"[{store_id}] Load failed: {output}")
        else:
            print(f"No events recorded for {store_id}.")


if __name__ == "__main__":

    print("Connecting to Snowflake...")
    sf_conn = get_snowflake_connection()
    sf_cursor = sf_conn.cursor()

    ensure_raw_table(sf_cursor)
    ensure_waste_table(sf_cursor)
    ensure_stockout_table(sf_cursor)

    # SALES
    extract(sf_conn, sf_cursor, "sales_events", "SALES_EVENTS",
            ["item_id", "quantity", "price", "created_at"])

    # WASTE
    extract(sf_conn, sf_cursor, "waste_log", "WASTE_LOG",
            ["item_id", "quantity", "created_at"])

    # STOCKOUT
    extract(sf_conn, sf_cursor, "stockout_events", "STOCKOUT_EVENTS",
            ["item_id", "quantity_requested", "created_at"])

    sf_cursor.close()
    sf_conn.close()
    print("Extract complete.")