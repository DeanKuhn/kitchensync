# KitchenSync Food Forecasting System

A portfolio project simulating a Kwik Trip-style Kitchen Production System (KPS). The system uses a real-time data pipeline, a multi-store Postgres architecture, a dbt-powered Snowflake analytics warehouse, and a LightGBM forecasting model to produce per-store food production plans — refreshed every 60 seconds.

---

## What This Project Demonstrates

- **Robust data pipeline engineering** — async POS event ingestion via FastAPI, per-store schema isolation in Neon (Postgres), and a sync pipeline into Snowflake
- **Modern analytics stack** — dbt Core transformations across staging → intermediate → mart layers with clean schema separation and column-level documentation
- **ML model development** — baseline scikit-learn model vs. production LightGBM, feature engineering from time-series sales data, cold-start handling for new menu items
- **Scalable architecture** — 12 simulated stores across 4 Midwest regions, each treated as an independent forecasting unit; config-file-driven menu allows items to be toggled without code changes
- **End-to-end thinking** — from raw POS event to kitchen staff production plan displayed in a live Streamlit dashboard with missed demand tracking

---

## System Architecture

```
[POS Simulator] ──POST /sales, /waste, /stockout──> [FastAPI Ingest API]
                                                              │
                                                              ▼
                                                     [Neon (Postgres)]
                                                     Per-store schemas
                                                              │
                                                    [extract_to_snowflake.py]
                                                              │
                                                              ▼
                                               [Snowflake — KS_DB.RAW]
                                         RAW.SALES_EVENTS + RAW.WASTE_LOG
                                                              │
                                                     [dbt Core pipeline]
                                                              │
                                          ┌───────────────────┴───────────────────┐
                                          ▼                                       ▼
                                    KS_DB.STAGING                      KS_DB.INTERMEDIATE
                                  stg_sales_events                int_sales__rolling_features
                                   stg_waste_log               int_sales__time_of_day_profile
                                                                                  │
                                                                                  ▼
                                                                          KS_DB.MARTS
                                                                        mart_store_sales
                                                                       mart_item_velocity
                                                                   mart_cold_start_profile
                                                                   mart_production_targets
                                                                    mart_waste_percentage
                                                                    mart_stockout_summary
                                                                                  │
                                                                       [ML Pipeline]
                                                                      ml/train.py (LightGBM)
                                                                      ml/predict.py → MARTS.PREDICTIONS
                                                                                  │
                                                                      [Streamlit Dashboard]
                                                              Per-store production queue (60s refresh)
                                                          NORMAL / URGENT flags + Missed Demand tracking
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Ingest API | FastAPI |
| POS Simulation | Python (async/httpx, Poisson arrivals, FIFO batch management) |
| Transactional DB | Neon (cloud Postgres) — per-store schemas |
| Analytics Warehouse | Snowflake |
| Transformations | dbt Core |
| ML — Baseline | scikit-learn (RandomForest) |
| ML — Production | LightGBM |
| Dashboard | Streamlit + streamlit-autorefresh |
| Config | YAML (menu items, store definitions) |
| Package Management | uv |

---

## How It Works

### 1. POS Simulation
An async Python simulator (httpx + asyncio) fires fake point-of-sale events to the ingest API, mimicking realistic store traffic using a Poisson distribution for customer arrivals and a time-of-day rush curve. Each store runs as an independent async task. A `StoreState` class tracks FIFO batch inventory — food is produced based on ML predictions, consumed when sold, and logged as waste when it expires past its hold time. Stockout events are fired when a customer requests an item with no inventory.

### 2. Ingest API
A FastAPI application receives live events and writes them to the appropriate store schema in Neon (Postgres). Each of the 12 stores has its own schema (`store_012`, `store_027`, etc.), demonstrating horizontal schema isolation. Three endpoints handle sales, waste, and stockout events.

### 3. Snowflake Extract
A Python script (`scripts/extract_to_snowflake.py`) pulls all sales and waste events from Neon and loads them into `KS_DB.RAW` in Snowflake. Full reload on each run.

### 4. dbt Pipeline
dbt Core transforms raw events through three layers in Snowflake:
- **Staging** — cleans and types raw events; derives `sale_date`, `sale_hour`, `day_of_week`
- **Intermediate** — computes rolling 2hr and 4hr sales aggregates; builds historical time-of-day demand profiles per store + item + hour + day-of-week
- **Marts** — business logic layer: production targets, item velocity and urgency flags, waste percentage, cold-start profiles, stockout summaries

### 5. ML Forecasting Model
A LightGBM model predicts units to produce per item per store. Features include time-of-day, day-of-week, rolling sales windows, and historical demand profiles. Items are flagged:
- `NORMAL` — demand is within historical norms
- `URGENT` — current sell-through rate exceeds historical average by 2x (configurable)

Items with fewer than 4 data points fall back to category-level averages from `mart_cold_start_profile`.

### 6. Streamlit Dashboard
An interactive dashboard refreshes every 60 seconds. Kitchen staff see a production queue with urgency flags, a "Mark Complete" checkbox per item (persisted in session state), and a missed demand column showing units lost to stockouts. A waste summary below shows Hot Foods, Roller Grill, and Chicken waste percentages for the most recent day.

---

## Project Structure

```
kitchensync/
├── config/                    # menu.yaml, stores.yaml
├── data/seeds/                # menu_items.csv (dbt seed)
├── simulator/
│   ├── pos_simulator.py       # Live async simulator (httpx + asyncio)
│   └── historical_generator.py # Batch historical data generator
├── api/
│   ├── main.py
│   ├── routes/events.py       # POST /sales, /waste, /stockout
│   ├── models/schemas.py      # Pydantic: SalesEvent, WasteEvent, StockoutEvent
│   └── db/connection.py       # Neon connection pool, per-store search_path
├── dbt/
│   ├── macros/generate_schema_name.sql
│   └── models/
│       ├── staging/           # stg_sales_events, stg_waste_log
│       ├── intermediate/      # int_sales__rolling_features, int_sales__time_of_day_profile
│       └── marts/             # mart_store_sales, mart_item_velocity, mart_cold_start_profile,
│                              # mart_production_targets, mart_waste_percentage, mart_stockout_summary
├── ml/                        # features.py, train.py, predict.py, evaluate.py
├── dashboard/
│   ├── app.py
│   ├── components/            # production_plan.py, waste_summary.py, store_selector.py
│   └── utils/data_fetch.py
└── scripts/
    ├── init_db.py             # One-time Neon schema + table creation
    ├── extract_to_snowflake.py
    └── run_pipeline.py        # Extract → dbt → train → predict
```

---

## Setup

### Prerequisites
- Python 3.12+
- uv (`pip install uv`)
- Neon account (free tier sufficient)
- Snowflake account (free trial sufficient)

### Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

```
NEON_DATABASE_URL=postgresql://...
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
SNOWFLAKE_DATABASE=KS_DB
SNOWFLAKE_WAREHOUSE=KS_WH
SNOWFLAKE_ROLE=
URGENCY_THRESHOLD=2.0
```

### Install Dependencies

```bash
uv sync
```

### Run the System

```bash
# 1. Initialize Neon schemas (one time)
PYTHONPATH=. uv run python scripts/init_db.py

# 2. Generate historical data (42 days)
PYTHONPATH=. uv run python simulator/historical_generator.py

# 3. Run the full pipeline (extract → dbt → train → predict)
PYTHONPATH=. uv run python -m scripts.run_pipeline

# 4. Start the ingest API
PYTHONPATH=. uv run uvicorn api.main:app --reload --port 8000

# 5. Start the live POS simulator (separate terminal)
PYTHONPATH=. uv run python simulator/pos_simulator.py

# 6. Launch the dashboard
PYTHONPATH=. uv run streamlit run dashboard/app.py
```

---

## Menu Configuration

Items are defined in `config/menu.yaml`. Key fields:

```yaml
- id: "CHEESEBURGER"
  name: "Cheeseburger"
  price: 2.99
  sale_price: 1.99
  sale_days: [2]      # Wednesday (0=Monday, 6=Sunday)
  cost: 1.20
  time_of_day: "all_day"   # all_day | breakfast | lunch | chicken
  category: "sandwich"     # sandwich | side | roller_grill | chicken | appetizer
  hold_time: 2
  popularity: 5
  active: true
  added: 2024-01-01
```

- Set `active: false` to retire an item — excluded from forecasting automatically
- Omit `sale_price` and `sale_days` for items that never go on sale
- `time_of_day` drives availability windows; `category` drives waste grouping and cold-start profiles

---

## dbt Commands

```bash
cd dbt

uv run dbt run                          # all models
uv run dbt run --select <model_name>    # single model
uv run dbt compile --select <model>     # syntax check only
uv run dbt seed                         # upload menu_items.csv to Snowflake
uv run dbt test                         # run data quality tests
```