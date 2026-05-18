# CLAUDE.md — KitchenSync Food Forecasting System

This file is the authoritative reference for Claude Code. Read it in full before taking any action in this project.

---

## Project Overview

A portfolio-grade simulation of a Kwik Trip-style Kitchen Production System (KPS). The system ingests real-time simulated POS (point-of-sale) events, stores them in a Postgres-backed transactional database, transforms them through a dbt pipeline into a Snowflake analytics warehouse, and feeds a LightGBM forecasting model that produces per-store, per-item production plans — refreshed every 5 minutes. A Streamlit dashboard surfaces results for kitchen staff.

This project exists to demonstrate: robust data pipeline engineering, scalable multi-store architecture, modern analytics stack (dbt + Snowflake), and ML model accuracy with real-time adaptation.

---

## Architecture Overview

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
| POS Simulation | Python script (randomized, time-aware) |
| Transactional DB | Neon (cloud Postgres) — per-store schemas |
| Analytics Warehouse | Snowflake |
| Transformation | dbt Core |
| ML — Baseline | scikit-learn (RandomForest or Ridge) |
| ML — Production | LightGBM |
| Dashboard | Streamlit |
| Data formats | Parquet (feature export/archiving), CSV (seed data) |
| Config | YAML (menu config, store config) |
| Package Management | uv |
| Dev environment | WSL, VS Code, Claude Code |

---

## Repository Structure

```
kitchensync/
├── CLAUDE.md
├── README.md
├── Dockerfile                 # Reference only
├── .env.example
├── pyproject.toml             # uv project config (name, version, requires-python)
│
├── config/
│   ├── menu.yaml              # Food items, areas, categories, hold times, active flags
│   └── stores.yaml            # 12 stores across 4 regions with traffic levels
│
├── data/
│   ├── seeds/
│   └── exports/
│
├── simulator/
│   ├── __init__.py
│   ├── pos_simulator.py       # Fires fake POS events to the ingest API
│   └── historical_generator.py # Generates ~2.7M synthetic events via psycopg2 batch inserts
│
├── api/
│   ├── __init__.py
│   ├── main.py                # FastAPI app entry point
│   ├── routes/
│   │   └── events.py          # POST endpoints: sales, waste, inventory
│   ├── models/
│   │   └── schemas.py         # Pydantic models: SalesEvent, WasteEvent, InventoryEvent
│   └── db/
│       └── connection.py      # Neon connection pool, get_store_connection() with search_path
│
├── dbt/
│   ├── dbt_project.yml        # Model paths, materialization config, schema assignments
│   ├── profiles.yml.example
│   ├── macros/
│   │   └── generate_schema_name.sql  # Overrides dbt schema prefixing behavior
│   ├── models/
│   │   ├── staging/
│   │   │   ├── sources.yml           # Registers KS_DB.RAW.SALES_EVENTS as a dbt source
│   │   │   └── stg_sales_events.sql  # Cleans/types raw events, derives sale_date/hour/dow
│   │   ├── intermediate/
│   │   │   ├── int_sales__rolling_features.sql      # Hourly aggregates + 1hr/4hr rolling sums
│   │   │   └── int_sales__time_of_day_profile.sql   # Historical avg demand by store/item/hour/dow
│   │   ├── marts/
│   │   └── metrics/
│   ├── tests/
│   ├── seeds/
│   └── snapshots/
│
├── ml/
│   ├── __init__.py
│   ├── features.py
│   ├── train.py
│   ├── predict.py
│   ├── evaluate.py
│   └── models/
│
├── dashboard/
│   ├── app.py
│   ├── components/
│   │   ├── production_plan.py
│   │   └── store_selector.py
│   └── utils/
│       └── data_fetch.py
│
├── scripts/
│   ├── init_db.py             # One-time Neon schema + table creation
│   └── extract_to_snowflake.py # Full reload: Neon → KS_DB.RAW.SALES_EVENTS
│
└── tests/
    ├── test_api.py
    ├── test_simulator.py
    └── test_ml_features.py
```

---

## Current State

### Completed
- All 12 store schemas created in Neon with `sales_events`, `waste_log`, `inventory_snapshots` tables
- FastAPI ingest API running with three endpoints (sales, waste, inventory)
- Historical data generator producing ~2.7M events across 12 stores, 90 days (Jan–Mar 2026)
- Snowflake provisioned: `KS_DB`, `KS_WH`, `RAW` schema
- Extract script loading all Neon data into `KS_DB.RAW.SALES_EVENTS`
- dbt project initialized, connected to Snowflake, `dbt debug` passing
- `generate_schema_name` macro in place for clean schema separation
- Staging model: `stg_sales_events` live in `KS_DB.STAGING`
- Intermediate models: `int_sales__rolling_features` and `int_sales__time_of_day_profile` live in `KS_DB.INTERMEDIATE`

### Next Up
- Mart models: `mart_store_sales` (wide fact table joining all features)
- Metrics models
- ML feature engineering and model training

---

## Database Design

### Neon (Postgres) — Transactional Layer

Each store gets its own schema: `store_012`, `store_027`, `store_034`, etc. (12 stores total)

Within each schema:

```sql
CREATE TABLE {store_id}.sales_events (
    id          SERIAL PRIMARY KEY,
    item_id     TEXT,
    quantity    INT,
    price       NUMERIC(10, 2),
    created_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE {store_id}.waste_log (
    id          SERIAL PRIMARY KEY,
    item_id     TEXT,
    quantity    INT,
    reason      TEXT,
    created_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE {store_id}.inventory_snapshots (
    id          SERIAL PRIMARY KEY,
    item_id     TEXT,
    quantity    INT,
    created_at  TIMESTAMP DEFAULT now()
);
```

### Snowflake — Analytics Layer

Database: `KS_DB`
Warehouse: `KS_WH`
Schemas: `RAW`, `STAGING`, `INTERMEDIATE`, `MARTS`, `METRICS`

#### RAW.SALES_EVENTS
```
STORE_ID     VARCHAR
ITEM_ID      VARCHAR
QUANTITY     INTEGER
PRICE        FLOAT
CREATED_AT   TIMESTAMP
```

---

## dbt Layer Design

### Key Configuration Notes
- Schema names are controlled via `+schema` in `dbt_project.yml`
- The `generate_schema_name` macro in `dbt/macros/` prevents dbt from prefixing schema names with the default target schema (e.g. `PUBLIC_STAGING` → `STAGING`)
- `profiles.yml` lives at `~/.dbt/profiles.yml` (outside the project), edit with `nano ~/.dbt/profiles.yml`

### Staging (`stg_`) — KS_DB.STAGING
- `stg_sales_events` — cleans and types raw events; derives `sale_date`, `sale_hour` (0–23), `day_of_week` (0=Sunday, 6=Saturday); filters null `created_at`

### Intermediate (`int_`) — KS_DB.INTERMEDIATE
- `int_sales__rolling_features` — aggregates sales to hourly buckets, then computes 1hr and 4hr rolling sums using SQL window functions (`ROWS BETWEEN N PRECEDING AND CURRENT ROW`)
- `int_sales__time_of_day_profile` — historical average quantity and sample size per store + item + day_of_week + sale_hour combination; used as baseline for urgency flag

### Marts (`mart_`) — KS_DB.MARTS
- `mart_store_sales` — wide fact table: store + item + time features + rolling aggregates (next to build)
- `mart_item_velocity` — current sell-through rate vs. historical baseline

### Metrics (`metrics_`) — KS_DB.METRICS
- `metrics_forecast_accuracy` — predicted vs. actual units (MAE, RMSE per item)
- `metrics_stockout_rate` — urgency flag trigger rate and justification tracking

---

## dbt Commands Reference

```bash
cd dbt

# Run a single model
uv run dbt run --select stg_sales_events

# Run multiple models
uv run dbt run --select stg_sales_events int_sales__rolling_features

# Run all models
uv run dbt run

# Compile only (no Snowflake execution — fast syntax check)
uv run dbt compile --select <model_name>

# Run tests
uv run dbt test
```

---

## ML Model Design

### Input Features
| Feature | Source |
|---|---|
| `hour_of_day` | `stg_sales_events.sale_hour` |
| `day_of_week` | `stg_sales_events.day_of_week` |
| `is_weekend` | Derived (day_of_week in 0, 6) |
| `rolling_1hr_units` | `int_sales__rolling_features` |
| `rolling_4hr_units` | `int_sales__rolling_features` |
| `avg_units_this_hour_dow` | `int_sales__time_of_day_profile` |
| `store_id` (encoded) | Store dimension |
| `item_id` (encoded) | Menu dimension |
| `days_since_item_added` | Cold-start feature |

### Output
- `predicted_units_next_1hr` — float, rounded to nearest integer for display
- `urgency_flag` — `NORMAL` or `URGENT` (threshold: 1.4x historical average, configurable)

### Cold-Start Logic
New items with fewer than 7 days of history fall back to category-level averages from `int_sales__time_of_day_profile`.

### Inference Cycle
Runs every 5 minutes. Pulls latest rolling features from Snowflake, produces production plan per store, writes results to a `predictions` table for the dashboard.

---

## Store Configuration

12 stores across 4 regions, defined in `config/stores.yaml`:

| Region | Stores |
|---|---|
| West Wisconsin | store_012, store_027, store_034 |
| South Wisconsin | store_056, store_061, store_078 |
| Minnesota | store_091, store_103, store_115 |
| Iowa | store_128, store_134, store_147 |

Traffic levels 1–4 control simulated sales volume. Hours are either `24/7` or `5am-11pm`.

---

## Menu Configuration

Defined in `config/menu.yaml`. Fields: `id`, `name`, `price`, `sale_price`, `area`, `category`, `hold_time`, `batch`, `active`, `added`.

Areas: `hot_spot`, `roller_grill`
Categories: `all_day`, `breakfast`, `lunch`, `chicken`

Items with `active: false` are excluded from forecasting. The chicken program (4 items) was added June 2025. `SAUSAGE_EGG_TORNADO` added July 2025. `CHICKEN_POT_PIE` discontinued.

---

## Environment Variables

```
# Neon (Postgres)
NEON_DATABASE_URL=postgresql://user:pass@host/dbname

# Snowflake
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
SNOWFLAKE_DATABASE=KS_DB
SNOWFLAKE_WAREHOUSE=KS_WH
SNOWFLAKE_ROLE=

# API
API_HOST=0.0.0.0
API_PORT=8000

# Simulator
SIMULATOR_INTERVAL_SECONDS=3
NUM_STORES=12
```

---

## Development Phases

### Phase 1 — Foundation ✅
- [x] Repo structure scaffolded
- [x] `config/menu.yaml` and `config/stores.yaml` created
- [x] Neon database provisioned, per-store schemas and tables created
- [x] FastAPI ingest API running (sales, waste, inventory endpoints)
- [x] Historical data generator (~2.7M events via psycopg2 batch inserts)
- [x] POS simulator

### Phase 2 — Data Pipeline 🔄
- [x] Snowflake provisioned (KS_DB, KS_WH)
- [x] Extract script (Neon → KS_DB.RAW.SALES_EVENTS)
- [x] dbt project initialized and connected to Snowflake
- [x] `generate_schema_name` macro for clean schema separation
- [x] Staging model (`stg_sales_events`)
- [x] Intermediate models (`int_sales__rolling_features`, `int_sales__time_of_day_profile`)
- [ ] Mart models (`mart_store_sales`, `mart_item_velocity`)
- [ ] Metrics models

### Phase 3 — ML Model
- [ ] Feature engineering script
- [ ] Baseline model (scikit-learn)
- [ ] LightGBM model
- [ ] Cold-start logic
- [ ] Urgency flag logic
- [ ] 5-minute inference loop

### Phase 4 — Dashboard
- [ ] Streamlit app skeleton
- [ ] Store selector
- [ ] Production plan table (NORMAL / URGENT)
- [ ] 5-minute auto-refresh

### Phase 5 — Polish & Stretch
- [ ] README finalized
- [ ] dbt metrics layer complete
- [ ] Model retraining pipeline (stretch)
- [ ] Weather feature (stretch)
- [ ] Dockerfile documented

---

## Key Design Decisions

1. **Per-store Postgres schemas** — simpler connection management via `search_path`, demonstrates schema-level isolation
2. **FastAPI over direct DB writes** — API-first design, more realistic to actual POS integrations
3. **psycopg2 batch inserts for historical data** — `execute_values()` for bulk loading vs. one-request-per-event (100x+ faster)
4. **LightGBM over Prophet** — allows feature engineering showcase; Prophet is a black box for interviews
5. **dbt Core (not Cloud)** — local/free, realistic for a dev environment
6. **`generate_schema_name` macro** — overrides dbt's default schema prefixing to produce clean `STAGING`, `INTERMEDIATE`, `MARTS`, `METRICS` schemas
7. **Config-file-driven menu** — items toggled without code changes; cold-start logic handles new items
8. **Snowflake as analytics layer** — separates transactional (Neon) and analytical (Snowflake) workloads