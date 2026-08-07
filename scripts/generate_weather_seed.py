"""Generator for the weather_daily seed -- writes both dbt/seeds/weather_daily.csv
(kept for the now-portfolio-only dbt project) and Neon public.weather_daily
(the copy the live pipeline actually reads).

Rebuilds from simulator.weather.get_weather() -- the same function
historical_generator.py / fast_historical_generator.py call -- so this can
never drift from what's actually reflected in sales_events. Re-run whenever
the historical window (START_DATE / day count) changes.
"""

import os
import csv
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import create_engine, text # type:ignore
from dotenv import load_dotenv # type:ignore

from simulator.weather import get_weather

load_dotenv()

# Kept in lockstep with historical_generator.py's START_DATE / 70-day window
# by hand rather than importing that module, since importing it would
# execute its top-level DB-writing script body as a side effect.
START_DATE = date(2026, 5, 20)
NUM_DAYS = 70

REGIONS = ["West Wisconsin", "South Wisconsin", "Minnesota", "Iowa"]

CSV_PATH = "dbt/seeds/weather_daily.csv"

rows = []
for region in REGIONS:
    for day_idx in range(NUM_DAYS):
        sim_date = START_DATE + timedelta(days=day_idx)
        weather = get_weather(region, sim_date)
        rows.append({
            "region": region,
            "sale_date": sim_date.isoformat(),
            "temp_f": round(weather["temp_f"], 1),
            "precip": weather["precip"],
        })

df = pd.DataFrame(rows)
df.to_csv(CSV_PATH, index=False)
print(f"Wrote {len(df)} rows to {CSV_PATH}")

engine = create_engine(os.getenv("NEON_DATABASE_URL"))
with engine.begin() as conn:
    conn.execute(text("SET search_path TO public;"))
    # sale_date is written as an ISO string in the CSV/dataframe above (fine
    # for the dbt seed); cast to an actual date dtype here so Postgres
    # stores a real DATE column instead of text, so joins against other
    # date-typed columns (e.g. sales_events derived dates) don't need an
    # explicit cast at query time.
    neon_df = df.copy()
    neon_df["sale_date"] = pd.to_datetime(neon_df["sale_date"]).dt.date
    neon_df.to_sql("weather_daily", conn, schema="public",
                    if_exists="replace", index=False)
print(f"Wrote {len(df)} rows to Neon public.weather_daily.")
