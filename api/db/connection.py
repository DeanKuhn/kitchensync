import os
from psycopg2 import pool
from dotenv import load_dotenv # type:ignore

load_dotenv()
database_url = os.getenv("NEON_DATABASE_URL")

if not database_url:
    raise ValueError("NEON_DATABASE_URL is not set in the .env file.")

# Connection pool reduces API overhead
# maxconn=50: FastAPI's sync route handlers run in Starlette's threadpool
# (default ~40 threads), so bursts up to ~40 concurrent requests are possible
# even without a code bug -- e.g. all 12 simulated stores crossing a 15-min
# slot boundary on the same tick. A cap of 10 raised PoolError under a
# measured 91-request burst on 2026-06-13 and 2026-07-07. 50 gives headroom
# above the threadpool ceiling; raise further if Neon's connection limit allows
# and bursts still exceed it.
connection_pool = pool.SimpleConnectionPool(1, 50, database_url)


def get_connection():
    return connection_pool.getconn()


def release_connection(connection):
    connection_pool.putconn(connection)


def get_store_connection(store_id: str):

    # Call get_connection() to get a regular connection
    connection = get_connection()

    # Set the search_path of the connection
    cursor = connection.cursor()
    cursor.execute(f"SET search_path TO {store_id}, public;")

    # Commit the transation-level command so it executes cleanly
    connection.commit()
    cursor.close()

    return connection