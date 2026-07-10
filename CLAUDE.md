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
                                                              (up to 12 stores
                                                               × 45 active items × 672 slots)
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
| ML — Baseline | Hourly average (in-memory, no model) |
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
├── Dockerfile                 # FastAPI ingest service image (production uses EC2 + systemd)
├── docker-compose.yml         # Full stack: API + simulator + dashboard
├── .env.example
├── pyproject.toml             # uv project config (name, version, requires-python)
│
├── config/
│   ├── menu.yaml              # Food items, categories, hold times, cook times, batch sizes, active flags
│   └── stores.yaml            # 12 stores across 4 regions with traffic levels
│
├── data/
│   ├── ab_results.json        # Nightly A/B output — tracked in git, consumed by Astro site
│   ├── seeds/
│   └── exports/
│
├── simulator/
│   ├── __init__.py
│   ├── pos_simulator.py       # Fires fake POS events to the ingest API
│   ├── historical_generator.py # Generates synthetic events via psycopg2 batch inserts (one execute_values call per day)
│   └── fast_historical_generator.py # Same generator logic, but batches each store's entire
│                                     # date range into a single execute_values call
│                                     # (page_size=10000) instead of one per day — ~100x fewer
│                                     # Neon round-trips. Prefer this for bulk (re)seeding.
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
│   ├── predict.py             # Inference: writes predictions to MARTS.PREDICTIONS (time-of-day filtered)
│   ├── evaluate.py
│   └── models/                # lgbm.joblib, store_encoder.joblib, item_encoder.joblib
│
├── dashboard/
│   ├── app.py                 # Streamlit entry point, 5-min autorefresh
│   ├── components/
│   │   ├── production_plan.py # Split Kitchen/Chicken queues, session state checkboxes
│   │   └── store_selector.py
│   └── utils/
│       └── data_fetch.py      # get_production_plan(), get_waste_summary() — predictions
│                                # from Snowflake, stockout/waste queried live from Neon
│
├── scripts/
│   ├── init_db.py             # One-time Neon schema + table creation
│   ├── extract_to_snowflake.py # Incremental (per-store watermark on created_at): Neon → KS_DB.RAW
│   ├── run_pipeline.py        # Nightly cron: extract → dbt → predict → A/B → git push (no train step)
│   ├── run_daily_simulation.py # A/B comparison — ML vs baseline, outputs data/ab_results.json
│   ├── delete_simulation_data.py # Wipes simulation data from BOTH Neon (delete_neon) and
│   │                              # Snowflake RAW (delete_snowflake) — run delete_snowflake alone
│   │                              # if Neon already has data you want to keep (e.g. a fresh reseed)
│   └── update_dbt_token.py
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
- Historical data generator (`historical_generator.py` / `fast_historical_generator.py`) — 6-week window, Poisson-based, sale-day aware; `START_DATE` is a constant at the top of the file, updated whenever the window is regenerated
- Live POS simulator — async/httpx, SimClock, StoreState FIFO inventory, slot-boundary production logic, cook times, batch sizes, RUSH_CURVE-scaled batch quantities, startup inventory seeding (rounded to a whole unit), 24-hour prediction reload
- Snowflake: `KS_DB`, `KS_WH`, `RAW.SALES_EVENTS`, `RAW.WASTE_LOG`, `RAW.STOCKOUT_EVENTS`
- Full dbt pipeline: staging → intermediate → marts (all models live, 15-min slot grain)
- LightGBM model trained, predictions (12 stores × 45 active items × 672 slots, minus off-window slots filtered per item's `time_of_day`) written to `MARTS.PREDICTIONS` — retrain via `python -m ml.train` then `python -m ml.predict` (no wrapper script; `run_training.py` no longer exists)
- Cold-start fallback via `mart_cold_start_profile` (category-level averages by slot_index, threshold = 4 samples)
- Streamlit dashboard: split Kitchen/Chicken production queues, current 15-min slot (anchored to Neon's own clock via `get_sim_now()`, not wall-clock, since the sim clock can drift from real time), missed demand, waste summary (units sold + total sales + waste %), 5-min autorefresh, session state checkboxes with completed items table, deployed live at [kitchensync.streamlit.app](https://kitchensync.streamlit.app) (Streamlit Community Cloud). Stockout/waste numbers are queried live from Neon (not the nightly Snowflake snapshot) as of the 2026-07-04/05 live-dashboard update; predictions still come from `MARTS.PREDICTIONS`.
- A/B comparison system: `run_daily_simulation.py` — in-memory, seeded by date, ML vs hourly-average baseline, outputs `data/ab_results.json`
- AWS EC2 deployment: API + simulator as systemd services (auto-restart on crash/reboot)
- Nightly cron pipeline: `git pull` → extract → dbt → predict → A/B comparison → git push (retraining is run manually); commit step guards against "nothing to commit" so a no-op day doesn't fail the whole run
- Portfolio site integration: `ab_results.json` committed to GitHub nightly, consumed by Astro static site
- Snowflake auth: RSA key pair (`~/.ssh/snowflake_rsa.p8`), registered via `ALTER USER`
- Two production-logic bugs found and fixed (2026-07-01/02) — see design decisions #18 and #19 below

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
| `is_weekend` | Derived (`day_of_week` in [5, 6]) |
| `avg_slot_quantity` | `int_sales__time_of_day_profile` |
| `sample_size` | `int_sales__time_of_day_profile` |
| `store_id` (encoded) | Store dimension |
| `item_id` (encoded) | Menu dimension |

### Output
- `predicted_units` — float, rounded to nearest integer
- Written to `MARTS.PREDICTIONS` with columns: `store_id`, `item_id`, `predicted_units`, `slot_index`, `predicted_at`
- Predictions cover all 672 slots × 12 stores × 45 active items, minus rows filtered out for being outside an item's `time_of_day` window (see `ml/predict.py`'s grid filter)

### Cold-Start Logic
Items with fewer than 4 data points fall back to category-level averages from `mart_cold_start_profile`, merging on `(category, slot_index)`.

### Inference
Reads all slots from `INT_SALES__TIME_OF_DAY_PROFILE`, runs warm (LightGBM) or cold (category avg) path per row, writes full weekly prediction table to `MARTS.PREDICTIONS` via `if_exists='replace'`.

---

## Simulator Design

### Key Parameters
- `TIME_SCALE = 20` — 1 real second = 20 simulated seconds
- `TICK_INTERVAL = 1` — real seconds per tick
- `START_TIME` — determined at startup by `get_start_time()`: queries `SELECT MAX(created_at) FROM RAW.SALES_EVENTS` in Snowflake and resumes from that timestamp; falls back to `datetime(2026, 7, 1, 0, 0, 0)` if Snowflake is empty (update this fallback whenever the historical seed window is regenerated with a new `START_DATE`)

### Production Logic
- Fires when `slot_idx != last_slot_idx and (is_rush or slot_idx % 4 == 0)`, where `is_rush = RUSH_CURVE[hour] >= 0.6`
- Per item, skips the cook decision entirely if `(not item["active"]) or (item["added"] > sim_now.date()) or (hour not in range(HOURS_AVAILABLE[item["time_of_day"]]))` — **must be an OR of the three skip-conditions**, not an AND; an AND collapses to always-False for active items and silently cooks off-window items 24/7 (this exact bug shipped and caused chronic overproduction — see design decision #18)
- `look_ahead = int(item["hold_time"] * 4)` slots
- `demand = sum(predictions for next look_ahead slots)`
- `committed = current_inventory + in_progress`
- `gap = demand - committed`
- `cook_qty = int(np.ceil(gap)) if gap > 1 else 0` — no minimum-batch floor; the old `scaled_batch = batch_size * 2 * RUSH_CURVE[hour]` floor was intentionally removed (commit `ccf1577`, 2026-06-14) because a floor forces low-traffic stores to overproduce relative to their thin demand. The remaining `ceil()`+`>1` threshold still imposes an implicit ~1-unit rounding tax per forced cook check, which is a known, accepted, conservative tradeoff — not a bug to "fix" by reintroducing a floor.

### Startup Seeding
On `StoreState` init, inventory is pre-seeded with the predicted units for the current slot per item (respecting `time_of_day` availability), **rounded to a whole number** (`predicted_units` from `MARTS.PREDICTIONS` is an unrounded float — every other cook-quantity code path rounds explicitly, and this one must too, or fractional quantities propagate through `consume()`/waste logging for the life of that batch; see design decision #19). Prevents stockout cascade before first slot boundary fires.

### Background Tasks
- `refresh_targets_task()` — loads `MARTS.PREDICTIONS` at startup and reloads every 24h (`asyncio.sleep(86400)`), not a one-time load
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

Defined in `config/menu.yaml`. Fields: `id`, `name`, `price`, `sale_price`, `sale_days`, `cost`, `time_of_day`, `category`, `hold_time`, `cook_time`, `batch`, `popularity`, `active`, `added`.

**`time_of_day`** — controls availability windows in the simulator:
- `all_day`: [0, 24]
- `breakfast`: [4, 12]
- `lunch`: [10, 22]
- `chicken`: [9, 22]

**`category`** — drives cold-start grouping and waste display:
- `sandwich`, `side`, `roller_grill`, `chicken`, `appetizer`

**`cook_time`** — minutes from order to ready (used for `ready_at` in simulator):
- `sandwich`: 10 min, `side`: 5 min, `roller_grill`: 10 min, `chicken`: 15 min, `appetizer`: 5 min

**`batch`** — no longer used by the production logic (the `scaled_batch`/`RUSH_CURVE`-floor formula that once read this field was removed, see design decision #11) — currently dead config, referenced nowhere in `*.py`

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
SNOWFLAKE_PRIVATE_KEY_PATH=~/.ssh/snowflake_rsa.p8  # defaults to this if not set

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
- [x] Inference writes predictions to `MARTS.PREDICTIONS` (12 stores × 45 active items × 672 slots, minus off-window rows filtered per item's `time_of_day`)

### Phase 4 — Dashboard ✅
- [x] Streamlit app with store selector
- [x] Split Kitchen / Chicken production queues (`st.data_editor` with checkboxes)
- [x] Current 15-min slot filtering (slot_index computed from wall-clock time)
- [x] Completed items table (done items removed from queue, shown separately)
- [x] Missed demand column (stockout units lost)
- [x] Waste summary (units sold + total sales + waste % per category)
- [x] 5-minute auto-refresh (`streamlit-autorefresh`)
- [x] Session state persistence for "Mark Complete" checkboxes

### Phase 5 — Polish ✅
- [x] CLAUDE.md updated
- [x] README updated
- [x] Dockerfile documented + docker-compose.yml added
- [ ] Weather feature (stretch)

### Phase 6 — A/B Comparison + AWS Deployment ✅
- [x] `run_daily_simulation.py` — in-memory ML vs baseline comparison
- [x] `data/ab_results.json` — daily + cumulative metrics output
- [x] AWS EC2 — API + simulator as systemd services
- [x] Nightly cron pipeline — extract → dbt → predict → A/B → git push
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
11. **No minimum-batch floor for cook quantities** *(superseded 2026-06-14, commit `ccf1577`)* — an earlier version scaled a minimum cook quantity by hourly traffic (`batch_size * 2 * RUSH_CURVE[hour]`) to avoid under-production during rush. This was deliberately removed: a floor forces low-traffic stores to overproduce relative to their genuinely thin demand, which is worse than the alternative. Current logic (`cook_qty = int(np.ceil(gap)) if gap > 1 else 0`) has no floor, only rounding.
12. **Retraining is manual** — cron runs extract → dbt → predict → A/B nightly but does not retrain the model. Retraining is triggered manually after significant data accumulation via `python -m ml.train` then `python -m ml.predict` (no wrapper script). The model is committed to git (`ml/models/lgbm.joblib`) so EC2 can pull a new model without running training on the t3.micro (which OOMs)
13. **A/B baseline never writes to Neon** — baseline system is purely in-memory metrics; only ML system generates training data; prevents baseline behavior from corrupting the model's learning signal
14. **Honest A/B finding** — ML achieves +1.6pp better service level (97.6% vs 96.1%) and ~40% fewer stockout events, at the cost of +3.3pp more waste (8.6% vs 5.3%); root cause is the ML system's production checks firing ~4x more often (every 15-min slot boundary vs. baseline's hourly), each subject to the same `ceil()`-driven ~1-unit rounding tax described in decision #11 — not a batch floor (there isn't one); a production system would need a cost function to balance the trade-off
15. **Conditional mean bias fix (2026-06-13)** — `int_sales__time_of_day_profile` originally averaged only over days with non-zero sales, making `avg_slot_quantity` a conditional mean (E[X|X>0]) instead of the true expected demand. For low-traffic stores this inflated predictions 3–4x. Fixed by computing `SUM(quantity) / total_dates` where `total_dates` counts all observed days for that store/day_of_week, including zero-sale days.
16. **Simulator restart resume** — `get_start_time()` queries `SELECT MAX(created_at) FROM RAW.SALES_EVENTS` at startup and uses that as `START_TIME`, so the simulation clock resumes from the last extracted timestamp rather than re-generating already-seen events. Falls back to a hardcoded date if Snowflake is empty — keep this fallback in sync with `START_DATE` in the historical generator whenever the seed window is regenerated. A small gap of un-extracted Neon events may be re-simulated after a restart, but the watermark on the extract blocks true duplicates from entering Snowflake.
17. **Snowflake RSA key path via env var** — `SNOWFLAKE_PRIVATE_KEY_PATH` defaults to `~/.ssh/snowflake_rsa.p8` if not set. Avoids hardcoding the EC2-specific absolute path and makes the Docker setup portable. Used in `ml/features.py` (SQLAlchemy engine) and `scripts/extract_to_snowflake.py` (connector).
18. **Production time-of-day gate must be OR, not AND (fixed 2026-07-02)** — `pos_simulator.py`'s per-item cook-decision skip check was written as `if (not item["active"] and item["added"] <= date and hour not in range(...)): continue`. Since `not item["active"]` is `False` for every real menu item, the whole `and`-chain collapsed to `False` and `continue` never fired — off-window items (e.g. chicken, available only 9am–10pm) got cook orders computed 24/7, with zero matching demand outside their window. This produced chronic overproduction concentrated at low-traffic stores (waste % inversely correlated with store traffic level: ~88% at level-1 stores vs. ~17% at level-4). Fixed to `if (not item["active"]) or (item["added"] > date) or (hour not in range(...)): continue` — an OR of the three skip-conditions, matching the (already-correct) positive filter used on the sales-generation side of the same file. `historical_generator.py` and `run_daily_simulation.py` were both already correct and unaffected.
19. **Startup-seeded inventory must be rounded (fixed 2026-07-02)** — `StoreState` startup seeding used the raw `predicted_units` sum from `MARTS.PREDICTIONS` directly as a batch `quantity`, without rounding. `predicted_units` is stored as an unrounded float; every other cook-quantity code path explicitly rounds (`int(np.ceil(gap))`), but this one didn't. Since `consume()` only subtracts whole-number sale quantities from a batch, the fractional remainder persisted through the batch's lifecycle and showed up as a fractional quantity in waste logs too, if the batch expired before selling out. Fixed with `seed_demand = round(seed_demand)`. Self-limiting even before the fix: seeding only runs once at simulator startup, so the fractional contamination fully flushes out (sold or wasted) within one `hold_time` window and never recurs.
