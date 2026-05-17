# One-time connection setup

from api.db.connection import get_connection
import yaml # type:ignore

# Get psycopg2 connection (Neon Postgres) from connection.py
connection = get_connection()

# Open the yaml file
with open("config/stores.yaml") as f:
    config = yaml.safe_load(f)

# Loop through each store in the yaml file
for store in config["stores"]:
    store_id = store["id"]

    cursor = connection.cursor()
    try:

        # Create schema with each store's id
        cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {store_id};")

        # Create sales_events table for each store
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {store_id}.sales_events(
            id SERIAL PRIMARY KEY,
            item_id TEXT,
            quantity INT,
            price NUMERIC(10, 2),
            created_at TIMESTAMP DEFAULT now());
            """)

        # Create waste_logs table for each store
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {store_id}.waste_log(
            id SERIAL PRIMARY KEY,
            item_id TEXT,
            quantity INT,
            reason TEXT,
            created_at TIMESTAMP DEFAULT now());
            """)

        # Create inventory_snapshots table for each store
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {store_id}.inventory_snapshots(
            id SERIAL PRIMARY KEY,
            item_id TEXT,
            quantity INT,
            created_at TIMESTAMP DEFAULT now());
            """)

        print(f"Schema and tables successfully created for {store_id}.")
        cursor.close()

    # Catch if a single store's schema fails to create, and make sure it does
    # not interrupt all other store schema creationss
    except Exception as e:
        print(f"Schema creation for {store_id} failed due to {e}")
        cursor.close()

connection.commit()
connection.close()