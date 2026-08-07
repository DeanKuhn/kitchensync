# Useful when you have a broken simulation and need to delete from
# a certain date forward


import yaml # type:ignore
from dotenv import load_dotenv # type:ignore

from api.db.connection import get_store_connection, release_connection

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


if __name__ == "__main__":
    print(f"Deleting all rows with created_at >= {CUTOFF}...")
    delete_neon()