# Useful when you have a broken simulation and need to delete from
# a certain date forward


import yaml # type:ignore
from sqlalchemy import text # type:ignore
from dotenv import load_dotenv # type:ignore

from api.db.connection import get_store_connection, release_connection
from ml.features import get_snowflake_engine

load_dotenv()

CUTOFF = "2027-01-01"   # High in case of accidental run

with open("config/stores.yaml", "r") as f:
    stores = yaml.safe_load(f)


def delete_neon():
    for store in stores["stores"]:
        store_id = store["id"]
        conn = get_store_connection(store_id)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM sales_events WHERE created_at >= %s", (CUTOFF,))
        cursor.execute("DELETE FROM waste_log WHERE created_at >= %s", (CUTOFF,))
        cursor.execute("DELETE FROM stockout_events WHERE created_at >= %s", (CUTOFF,))

        conn.commit()
        cursor.close()
        release_connection(conn)
        print(f"[{store_id}] Deleted simulation rows from Neon.")


def delete_snowflake():
    engine = get_snowflake_engine(schema="RAW")

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM RAW.SALES_EVENTS WHERE created_at >= :cutoff"), {"cutoff": CUTOFF})
        print("Deleted simulation rows from RAW.SALES_EVENTS.")

        conn.execute(text("DELETE FROM RAW.WASTE_LOG WHERE created_at >= :cutoff"), {"cutoff": CUTOFF})
        print("Deleted simulation rows from RAW.WASTE_LOG.")

        conn.execute(text("DELETE FROM RAW.STOCKOUT_EVENTS WHERE created_at >= :cutoff"), {"cutoff": CUTOFF})
        print("Deleted simulation rows from RAW.STOCKOUT_EVENTS.")


if __name__ == "__main__":
    print(f"Deleting all rows with created_at >= {CUTOFF}...")
    delete_neon()
    delete_snowflake()