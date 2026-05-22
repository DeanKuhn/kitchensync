# KitchenSync Food Forecasting System

A portfolio project simulating a Kwik Trip-style Kitchen Production System (KPS). The system uses a real-time data pipeline, a multi-store Postgres architecture, a dbt-powered Snowflake analytics warehouse, and a LightGBM forecasting model to produce per-store food production plans — refreshed every 5 minutes.

---

## What This Project Demonstrates

- **Robust data pipeline engineering** — real-time POS event ingestion via FastAPI, per-store schema isolation in Neon (Postgres), and a sync pipeline into Snowflake
- **Modern analytics stack** — dbt Core transformations across staging → intermediate → mart → metrics layers with clean schema separation
- **ML model development** — baseline scikit-learn model vs. production LightGBM, feature engineering from time-series sales data, cold-start handling for new menu items
- **Scalable architecture** — 12 simulated stores across 4 Midwest regions, each treated as an independent forecasting unit; config-file-driven menu allows items to be toggled without code changes
- **End-to-end thinking** — from raw POS event to kitchen staff production plan displayed in a live Streamlit dashboard

---

## System Architecture

```
[POS Simulator] ──POST /sale──> [FastAPI Ingest API]
                                        │
                                        ▼
                               [Neon (Postgres)]
                               Per-store schemas
                               (transactional layer)
                                        │
                               [extract_to_snowflake.py]
                                        │
                                        ▼
                          [Snowflake — KS_DB.RAW]
                                        │
                               [dbt Core pipeline]
                                        │
                          ┌─────────────┴─────────────┐
                          ▼                           ▼
                    KS_DB.STAGING            KS_DB.INTERMEDIATE
                  stg_sales_events      int_sales__rolling_features
                                      int_sales__time_of_day_profile
                                                    │
                                                    ▼
                                            KS_DB.MARTS
                                          mart_store_sales
                                         mart_item_velocity
                                                    │
                                                    ▼
                                           KS_DB.METRICS
                                      metrics_forecast_accuracy
                                        metrics_stockout_rate
                                                    │
                                          [Feature Engineering]
                                                    │
                                                    ▼
                                [LightGBM Forecasting Model]
                            (baseline: scikit-learn RandomForest)
                                                    │
                                                    ▼
                                      [Streamlit Dashboard]
                                Per-store production plan (5-min refresh)
                                    Items labeled NORMAL or URGENT
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Ingest API | FastAPI |
| POS Simulation | Python (randomized, time-aware traffic patterns) |
| Transactional DB | Neon (cloud Postgres) |
| Analytics Warehouse | Snowflake |
| Transformations | dbt Core |
| ML — Baseline | scikit-learn (RandomForest) |
| ML — Production | LightGBM |
| Dashboard | Streamlit |
| Config | YAML (menu items, store definitions) |
| Package Management | uv |

---

## How It Works

### 1. POS Simulation
A Python simulator fires fake point-of-sale events directly to Neon via psycopg2 batch inserts, mimicking realistic store traffic — busy at lunch, slow overnight. Each event carries a store ID, item ID, quantity, price, and timestamp. ~2.7 million historical events across 12 stores were generated covering 90 days.

### 2. Ingest API
A FastAPI application receives live sale events and writes them to the appropriate store schema in Neon (Postgres). Each of the 12 stores has its own schema (`store_012`, `store_027`, etc.), demonstrating horizontal schema isolation. Three endpoints handle sales, waste, and inventory events.

### 3. Snowflake Extract
A Python script (`scripts/extract_to_snowflake.py`) pulls all sales events from each store schema in Neon and loads them into a single `KS_DB.RAW.SALES_EVENTS` table in Snowflake with `store_id` added. Full reload on each run.

### 4. dbt Pipeline
dbt Core transforms raw sales events through four layers in Snowflake:
- **Staging** — cleans and types raw events, derives `sale_date`, `sale_hour`, `day_of_week`
- **Intermediate** — computes rolling 1hr and 4hr sales aggregates; builds historical time-of-day demand profiles
- **Marts** — wide fact tables combining store, item, time features, and rolling aggregates
- **Metrics** — forecast accuracy (MAE, RMSE) and stockout rate tracking

### 5. ML Forecasting Model
A LightGBM model trained on 90 days of synthetic historical data predicts **units to produce in the next 1 hour** per item per store. Features include time-of-day, day-of-week, rolling sales windows, and historical demand profiles.

Items are flagged:
- `NORMAL` — predicted demand is in line with historical patterns
- `URGENT` — current sell-through rate exceeds historical average by 1.4x or more (configurable)

New menu items with no history fall back to category-level averages until 7 days of data accumulates.

### 6. Streamlit Dashboard
A simple dashboard refreshes every 5 minutes showing the current production plan per store. Kitchen staff see a table of items with predicted units and urgency status.

---

## Project Structure

```
kitchensync/
├── config/                    # menu.yaml, stores.yaml
├── data/                      # Seed CSVs, parquet exports
├── simulator/                 # POS event simulator, historical data generator
├── api/                       # FastAPI ingest service
├── dbt/                       # dbt project (staging → intermediate → marts → metrics)
│   ├── macros/
│   │   └── generate_schema_name.sql   # Overrides dbt default schema prefixing
│   └── models/
│       ├── staging/
│       │   ├── sources.yml
│       │   └── stg_sales_events.sql
│       ├── intermediate/
│       │   ├── int_sales__rolling_features.sql
│       │   └── int_sales__time_of_day_profile.sql
│       ├── marts/
│       └── metrics/
├── ml/                        # Feature engineering, training, inference, evaluation
├── dashboard/                 # Streamlit app
├── scripts/                   # init_db.py, extract_to_snowflake.py
└── tests/                     # Unit tests for API, simulator, ML features
```

---

## Setup

### Prerequisites
- Python 3.12+
- uv (`pip install uv`)
- Neon account (free tier sufficient)
- Snowflake account (free trial sufficient)
- dbt Core installed (`uv add dbt-snowflake`)

### Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

Required variables:
```
NEON_DATABASE_URL=postgresql://...
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
SNOWFLAKE_DATABASE=KS_DB
SNOWFLAKE_WAREHOUSE=KS_WH
SNOWFLAKE_ROLE=
```

### Install Dependencies

```bash
uv sync
```

### Run the System

```bash
# 1. Initialize Neon schemas (one time)
PYTHONPATH=. uv run python scripts/init_db.py

# 2. Generate historical data
PYTHONPATH=. uv run python simulator/historical_generator.py

# 3. Extract to Snowflake
PYTHONPATH=. uv run python scripts/extract_to_snowflake.py

# 4. Run dbt transformations
cd dbt && uv run dbt run

# 5. Start the ingest API
PYTHONPATH=. uv run uvicorn api.main:app --reload --port 8000

# 6. Start the POS simulator (separate terminal)
PYTHONPATH=. uv run python simulator/pos_simulator.py

# 7. Train the forecasting model
PYTHONPATH=. uv run python ml/train.py

# 8. Launch the dashboard
uv run streamlit run dashboard/app.py
```

---

## dbt Notes

### Schema Configuration
dbt models are organized into four Snowflake schemas. A custom `generate_schema_name` macro in `dbt/macros/` overrides dbt's default behavior of prefixing schema names with the target schema, ensuring clean schema names (`STAGING`, `INTERMEDIATE`, `MARTS`, `METRICS`) instead of prefixed ones (`PUBLIC_STAGING`, etc.).

### Running Individual Models
```bash
cd dbt

# Run a single model
uv run dbt run --select stg_sales_events

# Run multiple models
uv run dbt run --select stg_sales_events int_sales__rolling_features

# Run all models
uv run dbt run
```

---

## Menu Configuration

Items are defined in `config/menu.yaml`. To add a new item:

```yaml
- id: "PRETZEL_CHEDDAR"
  name: "Cheddar Pretzel"
  area: "hot_spot"
  category: "lunch"
  active: true
  added: 2025-01-01
```

To retire an item, set `active: false`. Inactive items are excluded from forecasting automatically. New items with no history fall back to category-level averages until 7 days of data accumulates.

---

## Build Status

### Phase 1 — Foundation ✅
- [x] Repo scaffolded
- [x] Config files (menu, stores)
- [x] Neon provisioned, per-store schemas created
- [x] FastAPI ingest API (sales, waste, inventory endpoints)
- [x] Historical data generator (~2.7M events, 12 stores, 90 days)
- [x] POS simulator

### Phase 2 — Data Pipeline 🔄
- [x] Snowflake provisioned (KS_DB, KS_WH)
- [x] Extract script (Neon → Snowflake RAW)
- [x] dbt project initialized and connected
- [x] Staging model (`stg_sales_events`)
- [x] Intermediate models (`int_sales__rolling_features`, `int_sales__time_of_day_profile`)
- [x] Mart models
- [ ] Metrics models

### Phase 3 — ML Model
- [ ] Feature engineering
- [ ] Baseline model (scikit-learn)
- [ ] Production model (LightGBM)
- [ ] Cold-start logic
- [ ] Urgency flag logic
- [ ] 5-minute inference loop

### Phase 4 — Dashboard
- [ ] Streamlit skeleton
- [ ] Store selector
- [ ] Production plan table (NORMAL / URGENT)
- [ ] Auto-refresh

### Phase 5 — Polish
- [ ] README finalized
- [ ] dbt metrics layer complete
- [ ] Dockerfile (reference)

---

## Stretch Goals

| Goal | Notes |
|---|---|
| Weather feature | Open-Meteo API (free) — temperature and precipitation as model inputs |
| Auto-retraining pipeline | Weekly cron re-trains on last 90 days; replaces model if RMSE improves |
| Docker reference | `Dockerfile` present for containerization reference; not used in dev |