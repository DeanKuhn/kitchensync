# CLAUDE.md — KitchenSync Food Forecasting System

This file is the authoritative reference for Claude Code. Read it in full before taking any action in this project.

---

## Project Overview

A portfolio-grade simulation of a Kwik Trip-style Kitchen Production System (KPS). The system ingests real-time simulated POS (point-of-sale) events, stores them in a Postgres-backed transactional database, transforms them through a dbt pipeline into a Snowflake analytics warehouse, and feeds a LightGBM forecasting model that produces per-store, per-item production plans — refreshed every 5 minutes. A Streamlit dashboard surfaces results for kitchen staff.

This project exists to demonstrate: robust data pipeline engineering, scalable multi-store architecture, modern analytics stack (dbt + Snowflake), and ML model accuracy with real-time adaptation.

---

## Architecture Overview

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
| Transformation | dbt Core |
| ML — Baseline | scikit-learn (RandomForest) |
| ML — Production | LightGBM |
| Dashboard | Streamlit + streamlit-autorefresh |
| Data formats | CSV (seed data) |
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
- All 12 store schemas in Neon with `sales_events`, `waste_log`, `stockout_log` tables
- FastAPI ingest API with three endpoints: `/sales`, `/waste`, `/stockout`
- Historical data generator — 42 days (Jan 1 – Feb 11, 2026), Poisson-based, sale-day aware
- Live POS simulator — async/httpx, SimClock, StoreState FIFO inventory, stockout detection
- Snowflake: `KS_DB`, `KS_WH`, `RAW.SALES_EVENTS`, `RAW.WASTE_LOG`
- Full dbt pipeline: staging → intermediate → marts (all models live)
- LightGBM model trained, 540 store/item predictions written to `MARTS.PREDICTIONS`
- Cold-start fallback via `mart_cold_start_profile` (category-level averages)
- Streamlit dashboard: production queue, urgency flags, missed demand, waste summary
- `run_pipeline.py` orchestrates extract → dbt → train → predict in sequence

### Known Issues / In Progress
- `get_waste_summary()` in `data_fetch.py` still queries `area` column — needs updating to use `category` after menu schema change (area removed, category now drives waste grouping)
- `waste_summary.py` component grouping logic references old category names (`appetizers`, `sides`) — needs updating to `appetizer`, `side`

---

## Database Design

### Neon (Postgres) — Transactional Layer

Each store gets its own schema: `store_012`, `store_027`, `store_034`, etc. (12 stores total)

Within each schema:

```sql
CREATE TABLE sales_events (
    id          SERIAL PRIMARY KEY,
    item_id     TEXT,
    quantity    INT,
    price       NUMERIC(10, 2),
    created_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE waste_log (
    id          SERIAL PRIMARY KEY,
    item_id     TEXT,
    quantity    INT,
    created_at  TIMESTAMP DEFAULT now()
);

CREATE TABLE stockout_log (
    id                 SERIAL PRIMARY KEY,
    item_id            TEXT,
    quantity_requested INT,
    created_at         TIMESTAMP DEFAULT now()
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
- `stg_sales_events` — cleans and types raw events; derives `sale_date`, `sale_hour` (0–23), `day_of_week` (0=Monday, 6=Sunday); filters null `created_at`
- `stg_waste_log` — cleans waste events; derives `waste_date`, `waste_hour`

### Intermediate (`int_`) — KS_DB.INTERMEDIATE
- `int_sales__rolling_features` — aggregates sales to hourly buckets; computes 2hr and 4hr rolling sums via `ROWS BETWEEN N PRECEDING AND CURRENT ROW`
- `int_sales__time_of_day_profile` — historical average quantity and sample size per store + item + day_of_week + sale_hour; baseline for urgency flag and cold-start

### Marts (`mart_`) — KS_DB.MARTS
- `mart_store_sales` — wide fact table: store + item + time features + rolling aggregates; per-store latest row selected via `QUALIFY ROW_NUMBER() OVER (PARTITION BY store_id, item_id ORDER BY sale_date DESC, sale_hour DESC) = 1`
- `mart_item_velocity` — current sell-through rate vs. historical baseline; applies urgency threshold via dbt var; same per-store QUALIFY pattern
- `mart_cold_start_profile` — category-level average demand by hour + day_of_week; fallback for items with fewer than 4 data points
- `mart_production_targets` — prescriptive 15-minute slot inventory targets per store + item; drives simulator production logic
- `mart_waste_percentage` — monetary waste formula: `(waste_cost / sale_revenue) * 100` per store + item + date; joins to `PUBLIC.MENU_ITEMS` for cost and price
- `mart_stockout_summary` — total missed units per store + item + date + hour; joined to predictions in dashboard for missed demand display

**Critical pattern**: All mart models that need "latest snapshot per store" use `QUALIFY ROW_NUMBER() OVER (PARTITION BY store_id, item_id ORDER BY ...)` — never a global `LIMIT 1` or `ORDER BY ... LIMIT 1` CTE, which would silently filter to the most-advanced store only.

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

Defined in `config/menu.yaml`. Fields: `id`, `name`, `price`, `sale_price`, `sale_days`, `cost`, `time_of_day`, `category`, `hold_time`, `popularity`, `active`, `added`.

**`time_of_day`** — controls availability windows in the simulator:
- `all_day`: [0, 24]
- `breakfast`: [4, 12]
- `lunch`: [10, 22]
- `chicken`: [9, 22]

**`category`** — drives cold-start grouping and waste display:
- `sandwich`, `side`, `roller_grill`, `chicken`, `appetizer`

**Waste display mapping:**
- Hot Foods = `sandwich` + `side`
- Roller Grill = `roller_grill`
- Chicken = `chicken` + `appetizer`

**Sale pricing:** Items with `sale_days` and `sale_price` apply the discount on matching weekdays (0=Monday, 6=Sunday). Items without these fields always charge `price`.

Items with `active: false` are excluded from all forecasting and simulation. `CHICKEN_POT_PIE` is discontinued. Cold-start items (fewer than 4 data points) fall back to category-level averages from `mart_cold_start_profile`.

`menu_items.csv` in `dbt/seeds/` mirrors this file and must be kept in sync. After changing the CSV, run `DROP TABLE IF EXISTS KS_DB.PUBLIC.MENU_ITEMS` in Snowflake before `dbt seed`.

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
- [x] FastAPI ingest API (sales, waste, stockout endpoints)
- [x] Historical data generator (42 days, psycopg2 batch inserts, sale-day aware)
- [x] Live POS simulator (async/httpx, Poisson, FIFO inventory)

### Phase 2 — Data Pipeline ✅
- [x] Snowflake provisioned (KS_DB, KS_WH)
- [x] Extract script (Neon → RAW.SALES_EVENTS + RAW.WASTE_LOG)
- [x] dbt project initialized and connected to Snowflake
- [x] `generate_schema_name` macro for clean schema separation
- [x] Staging models (`stg_sales_events`, `stg_waste_log`)
- [x] Intermediate models (`int_sales__rolling_features`, `int_sales__time_of_day_profile`)
- [x] Mart models (store_sales, item_velocity, cold_start_profile, production_targets, waste_percentage, stockout_summary)
- [x] `run_pipeline.py` orchestration script

### Phase 3 — ML Model ✅
- [x] Feature engineering (`ml/features.py`)
- [x] Baseline model (scikit-learn RandomForest)
- [x] LightGBM model
- [x] Cold-start logic (category-level fallback, threshold = 4 samples)
- [x] Urgency flag (2.0x threshold, configurable via dbt var + .env)
- [x] Inference writes 540 store/item predictions to `MARTS.PREDICTIONS`

### Phase 4 — Dashboard ✅
- [x] Streamlit app with store selector
- [x] Interactive production queue (`st.data_editor` with checkboxes)
- [x] NORMAL / URGENT urgency flags with row highlighting
- [x] Missed demand column (stockout units lost)
- [x] Waste summary (Hot Foods / Roller Grill / Chicken percentages)
- [x] 60-second auto-refresh (`streamlit-autorefresh`)
- [x] Session state persistence for "Mark Complete" checkboxes

### Phase 5 — Polish 🔄
- [x] README updated
- [x] CLAUDE.md updated
- [ ] Waste dashboard query updated for new menu schema (area → category)
- [ ] Dockerfile documented
- [ ] Weather feature (stretch)
- [ ] Auto-retraining pipeline (stretch)

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