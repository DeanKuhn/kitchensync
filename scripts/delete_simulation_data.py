# Useful when you have a broken simulation and need to delete from
# a certain date forward


import os
import yaml # type:ignore
import snowflake.connector # type:ignore
from dotenv import load_dotenv # type:ignore

from api.db.connection import get_store_connection, release_connection

load_dotenv()

CUTOFF = "2025-01-01"

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


# def delete_snowflake():
#     conn = snowflake.connector.connect(
#         account=os.getenv("SNOWFLAKE_ACCOUNT"),
#         user=os.getenv("SNOWFLAKE_USER"),
#         private_key_file="/home/ubuntu/.ssh/snowflake_rsa.p8",
#         database=os.getenv("SNOWFLAKE_DATABASE"),
#         warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
#         role=os.getenv("SNOWFLAKE_ROLE"),
#         schema="RAW"
#     )
#     cursor = conn.cursor()

#     cursor.execute("DELETE FROM RAW.SALES_EVENTS WHERE created_at >= %s", (CUTOFF,))
#     print(f"Deleted simulation rows from RAW.SALES_EVENTS.")

#     cursor.execute("DELETE FROM RAW.WASTE_LOG WHERE created_at >= %s", (CUTOFF,))
#     print(f"Deleted simulation rows from RAW.WASTE_LOG.")

#     cursor.execute("DELETE FROM RAW.STOCKOUT_EVENTS WHERE created_at >= %s", (CUTOFF,))
#     print(f"Deleted simulation rows from RAW.STOCKOUT_EVENTS.")

#     cursor.execute("DELETE FROM MARTS.MART_WASTE_PERCENTAGE WHERE waste_date >= %s", (CUTOFF,))
#     print(f"Deleted simulation rows from MARTS.MART_WASTE_PERCENTAGE.")

#     cursor.execute("DELETE FROM MARTS.MART_STOCKOUT_SUMMARY WHERE stockout_date >= %s", (CUTOFF,))
#     print(f"Deleted simulation rows from MARTS.STOCKOUT_SUMMARY.")

#     cursor.close()
#     conn.close()


if __name__ == "__main__":
    print(f"Deleting all rows with created_at >= {CUTOFF}...")
    delete_neon()
    # delete_snowflake()