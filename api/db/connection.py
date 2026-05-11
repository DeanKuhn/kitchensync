# This file takes the NEON_DATABASE_URL from the .env file, loads it, and
# returns a working database connection that can be used in other areas of
# the project
#
# A connection pool is used to help with the overhead otherwise caused by
# repeatedly creating and ending connections to Neon


import os
from psycopg2 import pool # Needed for connection pool
from dotenv import load_dotenv # type:ignore


# Loads variables from .env into the environment
load_dotenv()

# Get the database url from the .env file loaded
database_url = os.getenv("NEON_DATABASE_URL")

# Raise error if the os can't find anything (gives back None)
if not database_url:
    raise ValueError("NEON_DATABASE_URL is not set in the .env file.")

# Create a connection pool to reduce API call overhead
connection_pool = pool.SimpleConnectionPool(1, 10, database_url)


def get_connection():

    # Returns a psycopg2 connection pool
    return connection_pool.getconn()


def release_connection(connection):

    # Returns connection when done
    connection_pool.putconn(connection)


def get_store_connection(store_id: str):

    # Call get_connection() to get a regular connection
    connection = get_connection()

    # Set the search_path of the connection to establish which store you are
    # working with
    cursor = connection.cursor()
    cursor.execute(f"SET search_path TO {store_id}, public;")

    # Commit the transation-level command so it executes cleanly
    connection.commit()
    cursor.close()

    # What this actually does:
    # The Neon database has many schemas since there are many stores
    # Each schema has it's own information, such as custom sales data
    #
    # If a connection without a search_path is opened and
    # SELECT * FROM sales_events;
    # is ran, Neon won't know which schema to open
    #
    # search_path allows every SQL execution or query on a schema using this
    # specific connection to add the {store_id} to the beginning of the
    # wanted rows
    #
    # So, for example, if this was queried:
    # SELECT * FROM sales_events;
    # with the proper search_path configured in the connection, it would
    # actually do this:
    # SELECT * FROM {store_id}.sales_events;
    # This saves both time and a lot of extra text in connection requests

    # Returns the connection to the appropriate store's schema
    return connection