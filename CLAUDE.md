# CLAUDE.md — KitchenSync Food Forecasting System

This file is the authoritative reference for Claude Code. Read it in full before taking any action in this project.

---

## Project Overview

A portfolio-grade simulation of a Kwik Trip-style Kitchen Production System (KPS). The system ingests real-time simulated POS (point-of-sale) events, stores them in a Postgres-backed transactional database, transforms them through a dbt pipeline into a Snowflake analytics warehouse, and feeds a LightGBM forecasting model that produces per-store, per-item production plans at 15-minute slot grain. A Streamlit dashboard surfaces results for kitchen staff, split into Kitchen and Chicken production queues.

An A/B comparison pipeline runs nightly on AWS EC2, comparing the ML system against a naive hourly-average baseline. Results are written to `data/ab_results.json`, committed to GitHub, and consumed by a static Astro portfolio site that updates automatically each morning.

This project exists to demonstrate: robust data pipeline engineering, scalable multi-store architecture, modern analytics stack (dbt + Snowflake), ML model accuracy with real-time adaptation, and automated cloud deployment.

---

## Architecture Overview

```
[POS Simulator — EC2 systemd] ──POST /sales, /waste, /stockout──> [FastAPI Ingest API — EC2 systemd]
                                                              │
                                                              ▼
                                                     [Neon (Postgres)]
                                                     Per-store schemas
                                                              │
                                              [Nightly cron — 2am UTC]
                                              extract_to_snowflake.py
                                                              │
                                                              ▼
                                               [Snowflake — KS_DB.RAW]
                                         RAW.SALES_EVENTS + RAW.WASTE_LOG
                                                    + RAW.STOCKOUT_EVENTS
                                                              │
                                                     [dbt Core pipeline]
                                                              │
                                          ┌───────────────────┴───────────────────┐
                                          ▼                                       ▼
                                    KS_DB.STAGING                      KS_DB.INTERMEDIATE
                                  stg_sales_events              int_sales__rolling_features_15min
                                   stg_waste_log               int_sales__time_of_day_profile
                                 stg_stockout_events
                                                                                  │
                                                                                  ▼
                                                                          KS_DB.MARTS
                                                                      mart_store_sales_15min
                                                                     mart_cold_start_profile
                                                                      mart_waste_percentage
                                                                      mart_stockout_summary
                                                                     mart_ml_training_features
                                                                                  │
                                                                         [ML Pipeline]
                                                                    ml/train.py (LightGBM)
                                                          ml/predict.py → MARTS.PREDICTIONS
                                                              (190,773 predictions: 12 stores
                                                               × 42 items × 672 slots)
                                                                                  │
                                                       ┌──────────────────────────┴──────────────────────────┐
                                                       ▼                                                     ▼
                                           [Streamlit Dashboard]                          [A/B Comparison — run_daily_simulation.py]
                                  Split Kitchen / Chicken production queues                ML (15-min grain) vs Baseline (hourly avg)
                                  Current 15-min slot | 5-min auto-refresh                     In-memory, seeded by date
                                       Missed Demand + Waste Summary                                        │
                                                                                                            ▼
                                                                                               data/ab_results.json
                                                                                                            │
                                                                                           git commit + push (GitHub Actions)
                                                                                                            │
                                                                                               [Astro Portfolio Site]
                                                                                          Daily ML vs Baseline metrics display
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
| A/B Comparison | Pure Python in-memory simulation |
| Portfolio Site | Static Astro site, fed by ab_results.json |
| Cloud Hosting | AWS EC2 (systemd services + cron) |
| Data formats | CSV (seed data), JSON (A/B results) |
| Config | YAML (menu config, store config) |
| Package Management | uv |
| Dev environment | WSL, VS Code, Claude Code |
| Auth | Snowflake RSA key pair (~/.ssh/snowflake_rsa.p8) |

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
│   ├── menu.yaml              # Food items, categories, hold times, cook times, batch sizes, active flags
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
│   │   └── events.py          # POST endpoints: /sales, /waste, /stockout
│   ├── models/
│   │   └── schemas.py         # Pydantic models: SalesEvent, WasteEvent, StockoutEvent
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
│   │   │   ├── sources.yml                        # Registers KS_DB.RAW as dbt sources
│   │   │   ├── stg_sales_events.sql               # Cleans raw events, derives sale_date/hour/dow/minute/slot_index
│   │   │   └── stg_waste_log.sql                  # Cleans waste events, derives waste_date/hour
│   │   ├── intermediate/
│   │   │   ├── int_sales__rolling_features_15min.sql  # 15-min slot aggregates per store/item
│   │   │   └── int_sales__time_of_day_profile.sql     # Historical avg demand by store/item/slot_index
│   │   └── marts/
│   │       ├── mart_store_sales_15min.sql         # Wide fact table at 15-min grain, latest slot per store/item
│   │       ├── mart_cold_start_profile.sql        # Category-level avg demand by slot_index, cold-start fallback
│   │       ├── mart_waste_percentage.sql          # Waste cost / sale revenue per store/item/date
│   │       └── mart_stockout_summary.sql          # Missed units per store/item/date/hour
│   ├── tests/
│   ├── seeds/
│   └── snapshots/
│
├── ml/
│   ├── __init__.py
│   ├── features.py            # FEATURE_COLS, get_snowflake_engine()
│   ├── train.py               # LightGBM training, saves lgbm.joblib + encoders
│   ├── predict.py             # Inference: writes 190,773 predictions to MARTS.PREDICTIONS
│   ├── evaluate.py
│   └── models/                # lgbm.joblib, store_encoder.joblib, item_encoder.joblib
│
├── dashboard/
│   ├── app.py                 # Streamlit entry point, 5-min autorefresh
│   ├── components/
│   │   ├── production_plan.py # Split Kitchen/Chicken queues, session state checkboxes
│   │   └── store_selector.py
│   └── utils/
│       └── data_fetch.py      # get_production_plan(), get_waste_summary()
│
├── scripts/
│   ├── init_db.py             # One-time Neon schema + table creation
│   ├── extract_to_snowflake.py # Full reload: Neon → KS_DB.RAW
│   ├── run_prediction_update.py # extract → dbt → predict (no train; runs every 5 min in simulator)
│   ├── run_training.py        # Full pipeline including train step (run manually before simulation)
│   └── delete_simulation_data.py # Wipes live simulation data from Neon for a clean restart
│
└── tests/
    ├── test_api.py
    ├── test_simulator.py
    └── test_ml_features.py
```

---

## Current State

### Completed
- All 12 store schemas in Neon with `sales_events`, `waste_log`, `stockout_events` tables
- FastAPI ingest API with three endpoints: `/sales`, `/waste`, `/stockout`
- Historical data generator — 42 days (Jan 1 – Feb 11, 2026), Poisson-based, sale-day aware
- Live POS simulator — async/httpx, SimClock, StoreState FIFO inventory, slot-boundary production logic, cook times, batch sizes, RUSH_CURVE-scaled batch quantities, startup inventory seeding, 24-hour prediction reload
- Snowflake: `KS_DB`, `KS_WH`, `RAW.SALES_EVENTS`, `RAW.WASTE_LOG`, `RAW.STOCKOUT_EVENTS`
- Full dbt pipeline: staging → intermediate → marts (all models live, 15-min slot grain)
- LightGBM model trained, 190,773 predictions (12 stores × 42 items × 672 slots) written to `MARTS.PREDICTIONS`
- Cold-start fallback via `mart_cold_start_profile` (category-level averages by slot_index, threshold = 4 samples)
- Streamlit dashboard: split Kitchen/Chicken production queues, current 15-min slot, missed demand, waste summary (units sold + total sales + waste %), 5-min autorefresh, session state checkboxes with completed items table
- A/B comparison system: `run_daily_simulation.py` — in-memory, seeded by date, ML vs hourly-average baseline, outputs `data/ab_results.json`
- AWS EC2 deployment: API + simulator as systemd services (auto-restart on crash/reboot)
- Nightly cron pipeline: extract → dbt → retrain → predict → A/B comparison → git push
- Portfolio site integration: `ab_results.json` committed to GitHub nightly, consumed by Astro static site
- Snowflake auth: RSA key pair (`~/.ssh/snowflake_rsa.p8`), registered via `ALTER USER`

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

CREATE TABLE stockout_events (
    id                 SERIAL PRIMARY KEY,
    item_id            TEXT,
    quantity_requested INT,
    created_at         TIMESTAMP DEFAULT now()
);
```

### Snowflake — Analytics Layer

Database: `KS_DB`
Warehouse: `KS_WH`
Schemas: `RAW`, `STAGING`, `INTERMEDIATE`, `MARTS`, `PUBLIC`

#### RAW.SALES_EVENTS
```
STORE_ID     VARCHAR
ITEM_ID      VARCHAR
QUANTITY     INTEGER
PRICE        FLOAT
CREATED_AT   TIMESTAMP
```

#### RAW.WASTE_LOG
```
STORE_ID     VARCHAR
ITEM_ID      VARCHAR
QUANTITY     INTEGER
CREATED_AT   TIMESTAMP
```

---

## dbt Layer Design

### Key Configuration Notes
- Schema names are controlled via `+schema` in `dbt_project.yml`
- The `generate_schema_name` macro in `dbt/macros/` prevents dbt from prefixing schema names with the default target schema (e.g. `PUBLIC_STAGING` → `STAGING`)
- `profiles.yml` lives at `~/.dbt/profiles.yml` (outside the project), edit with `nano ~/.dbt/profiles.yml`
- All dbt commands run from the project root using `--project-dir dbt`

### Staging (`stg_`) — KS_DB.STAGING
- `stg_sales_events` — cleans and types raw events; derives `sale_date`, `sale_hour` (0–23), `sale_minute`, `day_of_week` (0=Monday, 6=Sunday), `slot_index`; filters null `created_at`
- `stg_waste_log` — cleans waste events; derives `waste_date`, `waste_hour`

### Intermediate (`int_`) — KS_DB.INTERMEDIATE
- `int_sales__rolling_features_15min` — aggregates sales to 15-minute slot buckets per store/item
- `int_sales__time_of_day_profile` — historical average quantity and sample size per store + item + day_of_week + sale_hour + sale_minute + slot_index; primary feature source for ML inference

### Marts (`mart_`) — KS_DB.MARTS
- `mart_store_sales_15min` — wide fact table at 15-min grain; per-store latest slot selected via `QUALIFY ROW_NUMBER() OVER (PARTITION BY store_id, item_id ORDER BY sale_date DESC, slot_index DESC) = 1`
- `mart_cold_start_profile` — category-level average demand by slot_index; fallback for items with fewer than 4 data points
- `mart_waste_percentage` — monetary waste formula: `(waste_cost / sale_revenue) * 100` per store + item + date; includes `sale_quantity` for units sold display; joins to `PUBLIC.MENU_ITEMS` for cost and price
- `mart_stockout_summary` — total missed units per store + item + date + hour; joined to predictions in dashboard for missed demand display

**Critical pattern**: All mart models that need "latest snapshot per store" use `QUALIFY ROW_NUMBER() OVER (PARTITION BY store_id, item_id ORDER BY ...)` — never a global `LIMIT 1` or `ORDER BY ... LIMIT 1` CTE, which would silently filter to the most-advanced store only.

**Slot index formula**: `(day_of_week * 96) + (sale_hour * 4) + FLOOR(sale_minute / 15)`, range 0–671, wraps with `% 672`. Uses 0=Monday convention.

---

## dbt Commands Reference

```bash
# Run a single model (from project root)
uv run dbt run --project-dir dbt --select stg_sales_events

# Run multiple models
uv run dbt run --project-dir dbt --select stg_sales_events int_sales__rolling_features_15min

# Run all models
uv run dbt run --project-dir dbt

# Compile only (no Snowflake execution — fast syntax check)
uv run dbt compile --project-dir dbt --select <model_name>

# Run tests
uv run dbt test --project-dir dbt
```

---

## ML Model Design

### Input Features
| Feature | Source |
|---|---|
| `sale_hour` | `int_sales__time_of_day_profile` |
| `sale_minute` | `int_sales__time_of_day_profile` |
| `slot_index` | `int_sales__time_of_day_profile` |
| `day_of_week` | `int_sales__time_of_day_profile` |
| `is_weekend` | Derived (`day_of_week` in [0, 6]) |
| `avg_slot_quantity` | `int_sales__time_of_day_profile` |
| `sample_size` | `int_sales__time_of_day_profile` |
| `store_id` (encoded) | Store dimension |
| `item_id` (encoded) | Menu dimension |

### Output
- `predicted_units` — float, rounded to nearest integer
- Written to `MARTS.PREDICTIONS` with columns: `store_id`, `item_id`, `predicted_units`, `slot_index`, `predicted_at`
- 190,773 total predictions covering all 672 slots × 12 stores × 42 items

### Cold-Start Logic
Items with fewer than 4 data points fall back to category-level averages from `mart_cold_start_profile`, merging on `(category, slot_index)`.

### Inference
Reads all slots from `INT_SALES__TIME_OF_DAY_PROFILE`, runs warm (LightGBM) or cold (category avg) path per row, writes full weekly prediction table to `MARTS.PREDICTIONS` via `if_exists='replace'`.

---

## Simulator Design

### Key Parameters
- `TIME_SCALE = 20` — 1 real second = 20 simulated seconds
- `TICK_INTERVAL = 1` — real seconds per tick
- `START_TIME = datetime(2026, 2, 12, 0, 0, 0)` — simulation start (day after historical data ends)

### Production Logic
- Fires once per 15-min slot boundary (`slot_idx != last_slot_idx`)
- `look_ahead = int(item["hold_time"] * 4)` slots
- `demand = sum(predictions for next look_ahead slots)`
- `committed = current_inventory + in_progress`
- `gap = demand - committed`
- `cook_qty = max(scaled_batch, gap) if gap > 0 else 0`
- `scaled_batch = max(1, round(item["batch_size"] * 2 * RUSH_CURVE[hour]))` — batch size scales with traffic level

### Startup Seeding
On `StoreState` init, inventory is pre-seeded with the predicted units for the current slot per item (respecting `time_of_day` availability). Prevents stockout cascade before first slot boundary fires.

### Background Tasks
- `refresh_targets_task()` — loads `MARTS.PREDICTIONS` once at startup, does not repeat
- `refresh_pipeline_task()` — runs extract + dbt every 300 seconds during simulation (no predict, no train)

### Running the Simulator
```bash
# Start the API first
PYTHONPATH=. uv run uvicorn api.main:app --host 0.0.0.0 --port 8000

# Start the dashboard
PYTHONPATH=. uv run streamlit run dashboard/app.py

# Start the simulator
PYTHONPATH=. uv run python -m simulator.pos_simulator
```

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

Defined in `config/menu.yaml`. Fields: `id`, `name`, `price`, `sale_price`, `sale_days`, `cost`, `time_of_day`, `category`, `hold_time`, `cook_time`, `batch_size`, `popularity`, `active`, `added`.

**`time_of_day`** — controls availability windows in the simulator:
- `all_day`: [0, 24]
- `breakfast`: [4, 12]
- `lunch`: [10, 22]
- `chicken`: [9, 22]

**`category`** — drives cold-start grouping and waste display:
- `sandwich`, `side`, `roller_grill`, `chicken`, `appetizer`

**`cook_time`** — minutes from order to ready (used for `ready_at` in simulator):
- `sandwich`: 10 min, `side`: 5 min, `roller_grill`: 10 min, `chicken`: 15 min, `appetizer`: 5 min

**`batch_size`** — minimum realistic cook quantity per item; scaled by `RUSH_CURVE[hour] * 2` during production logic

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
- [x] Intermediate models (`int_sales__rolling_features_15min`, `int_sales__time_of_day_profile`)
- [x] Mart models (`mart_store_sales_15min`, `mart_cold_start_profile`, `mart_waste_percentage`, `mart_stockout_summary`)
- [x] Pipeline scripts: `run_prediction_update.py` (extract + dbt), `run_training.py` (full pipeline)

### Phase 3 — ML Model ✅
- [x] Feature engineering (`ml/features.py`)
- [x] Baseline model (scikit-learn RandomForest)
- [x] LightGBM model at 15-min slot grain
- [x] Cold-start logic (category-level fallback, threshold = 4 samples)
- [x] Inference writes 190,773 predictions to `MARTS.PREDICTIONS` (12 stores × 42 items × 672 slots)

### Phase 4 — Dashboard ✅
- [x] Streamlit app with store selector
- [x] Split Kitchen / Chicken production queues (`st.data_editor` with checkboxes)
- [x] Current 15-min slot filtering (slot_index computed from wall-clock time)
- [x] Completed items table (done items removed from queue, shown separately)
- [x] Missed demand column (stockout units lost)
- [x] Waste summary (units sold + total sales + waste % per category)
- [x] 5-minute auto-refresh (`streamlit-autorefresh`)
- [x] Session state persistence for "Mark Complete" checkboxes

### Phase 5 — Polish 🔄
- [x] CLAUDE.md updated
- [x] README updated
- [ ] Dockerfile documented
- [ ] Weather feature (stretch)

### Phase 6 — A/B Comparison + AWS Deployment ✅
- [x] `run_daily_simulation.py` — in-memory ML vs baseline comparison
- [x] `data/ab_results.json` — daily + cumulative metrics output
- [x] AWS EC2 — API + simulator as systemd services
- [x] Nightly cron pipeline — extract → dbt → retrain → predict → A/B → git push
- [x] Portfolio site integration — Astro site reads ab_results.json from GitHub
- [x] Snowflake RSA key pair auth

---

## Key Design Decisions

1. **Per-store Postgres schemas** — simpler connection management via `search_path`, demonstrates schema-level isolation; intentionally does not scale past ~50 stores (DDL migrations across hundreds of schemas become painful at Kwik Trip scale)
2. **Transactional isolation vs. analytical consolidation** — per-store schemas in Neon for writes; single `store_id`-keyed table in Snowflake for cross-store analytics and model training
3. **FastAPI over direct DB writes** — API-first design, more realistic to actual POS integrations
4. **psycopg2 batch inserts for historical data** — `execute_values()` for bulk loading vs. one-request-per-event (100x+ faster)
5. **LightGBM over Prophet** — allows feature engineering showcase; Prophet is a black box for interviews
6. **15-min slot grain for ML** — matches real KPS production planning cycle; 672 slots/week covers the full weekly demand profile per store/item
7. **dbt Core (not Cloud)** — local/free, realistic for a dev environment
8. **`generate_schema_name` macro** — overrides dbt's default schema prefixing to produce clean `STAGING`, `INTERMEDIATE`, `MARTS` schemas
9. **Config-file-driven menu** — items toggled without code changes; cold-start logic handles new items
10. **Slot-boundary production logic** — cook decisions fire once per 15-min boundary, not every tick; look-ahead window = `hold_time * 4` slots
11. **RUSH_CURVE-scaled batch sizes** — minimum cook quantity scales with hourly traffic to prevent over-production during dead hours and under-production during rush
12. **Nightly retraining loop** — simulator runs 24/7 generating events; cron retrains nightly; simulator reloads predictions every 24 hours; A/B comparison always reads fresh predictions
13. **A/B baseline never writes to Neon** — baseline system is purely in-memory metrics; only ML system generates training data; prevents baseline behavior from corrupting the model's learning signal
14. **Honest A/B finding** — ML reduces stockouts ~31% vs baseline but increases waste ~5.5%; root cause is 4x more production checks + minimum batch size; a production system would need a cost function to balance the trade-off
