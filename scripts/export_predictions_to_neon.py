# One-time (and retrain-time) export: Snowflake MARTS.PREDICTIONS -> Neon.
# The dashboard and A/B sim read predictions from Neon so they never need
# Snowflake compute running. Re-run this as the last step of any manual
# retrain (see CLAUDE.md retrain playbook) after ml.predict refreshes
# MARTS.PREDICTIONS in Snowflake.


import os
import pandas as pd
from sqlalchemy import text, create_engine # type:ignore
from dotenv import load_dotenv # type:ignore

from ml.features import get_snowflake_engine

load_dotenv()


def fetch_predictions():
    engine = get_snowflake_engine()

    query = text("""
        select store_id, item_id, slot_index, predicted_units
        from MARTS.PREDICTIONS
    """)

    df = pd.read_sql(query, engine)
    df.columns = df.columns.str.lower()

    return df


def write_predictions(df):
    engine = create_engine(os.getenv("NEON_DATABASE_URL"))

    with engine.begin() as conn:
        conn.execute(text("SET search_path TO public;"))
        df.to_sql("predictions", conn, schema="public",
                   if_exists="replace", index=False, chunksize=10000)

    print(f"[EXPORT] Wrote {len(df)} rows to public.predictions.")


if __name__ == "__main__":
    predictions_df = fetch_predictions()
    write_predictions(predictions_df)
