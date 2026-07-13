import os
from psycopg2 import pool
from dotenv import load_dotenv # type:ignore

load_dotenv()
database_url = os.getenv("NEON_DATABASE_URL")

if not database_url:
    raise ValueError("NEON_DATABASE_URL is not set in the .env file.")

# Connection pool reduces API overhead, raised from 10 to 50
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