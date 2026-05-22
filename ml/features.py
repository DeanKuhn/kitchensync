# Feature engineering from mart/intermediate models

# 1. Connect to Snowflake
# 2. Query mart_store_sales and pull those columns
# 3. Add is_weekend and return the DataFrame

import os
import pandas as pd
import snowflake.connector # type:ignore
from dotenv import load_dotenv # type:ignore

load_dotenv()


def get_snowflake_connection():
    return snowflake.connector.connect(
        account=os.getenv("SNOWFLAKE_ACCOUNT"),
        user=os.getenv("SNOWFLAKE_USER"),
        password=os.getenv("SNOWFLAKE_PASSWORD"),
        database=os.getenv("SNOWFLAKE_DATABASE"),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
        role=os.getenv("SNOWFLAKE_ROLE"),
        schema="MARTS"
    )


def load_features():

    connection = get_snowflake_connection()

    query = """
        select
            store_id,
            item_id,
            sale_date,
            sale_hour,
            day_of_week,
            hourly_quantity,
            rolling_2hr,
            rolling_4hr,
            avg_hourly_quantity,
            sample_size

        from MARTS.MART_STORE_SALES
        where sample_size >= 10
    """

    df = pd.read_sql(query, connection)
    connection.close()

    # Make columns lowercase so they're easier to work with
    df.columns = df.columns.str.lower()

    # Adds new column: 1 if Saturday or Sunday, 0 else
    df['is_weekend'] = df['day_of_week'].isin([0, 6]).astype(int)

    return df


# For testing
# if __name__ == "__main__":
#     df = load_features()
#     print(df.shape)
#     print(df.head())
#     print(df.dtypes)