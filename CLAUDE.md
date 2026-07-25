# CLAUDE.md — KitchenSync Food Forecasting System

This file is the authoritative reference for Claude Code. Read it in full before taking any action in this project.

---

## Project Overview

A portfolio-grade simulation of a Kwik Trip-style Kitchen Production System (KPS). The system ingests real-time simulated POS (point-of-sale) events, stores them in a Postgres-backed transactional database (Neon), and feeds a LightGBM forecasting model that produces per-store, per-item production plans at 15-minute slot grain. A Streamlit dashboard surfaces results for kitchen staff, split into Kitchen and Chicken production queues.

An A/B comparison pipeline runs nightly on AWS EC2, comparing the ML system against a naive hourly-average baseline. Results are written to `data/ab_results.json`, committed to GitHub, and consumed by a static Astro portfolio site that updates automatically each morning.

**Snowflake is off the nightly/live hot path as of 2026-07-25** (design decision #20) — cost-driven migration. `MARTS.PREDICTIONS` is exported to a Neon table (`public.predictions`) and the dbt `int_sales__time_of_day_profile` baseline logic is replicated directly against Neon nightly (`scripts/build_baseline_profile.py` → `public.baseline_profile`). The dashboard, simulator, and A/B pipeline all read from Neon only. Snowflake stays suspended (not dropped) and is resumed manually only for retraining — see the retrain playbook below.

This project exists to demonstrate: robust data pipeline engineering, scalable multi-store architecture, a modern analytics stack (dbt + Snowflake, used for training), ML model accuracy with real-time adaptation, and automated cloud deployment on a cost-conscious footprint.

---

## Architecture Overview

```
[POS Simulator — EC2 systemd] ──POST /sales, /waste, /stockout──> [FastAPI Ingest API — EC2 systemd]
                                                              │
                                                              ▼
                                                     [Neon (Postgres)]
                                                     Per-store schemas
                                              + shared public.predictions
                                              + shared public.baseline_profile
                                                              │
                                              [Nightly cron — 2am UTC]
                                          scripts/build_baseline_profile.py
                                    (ports dbt's time_of_day_profile logic to Neon SQL,
                                     rebuilds public.baseline_profile from raw sales_events)
                                                              │
                                          ┌───────────────────┴───────────────────┐
                                          ▼                                       ▼
                              [Streamlit Dashboard]                  [A/B Comparison — run_daily_simulation.py]
                     Split Kitchen / Chicken production queues        ML (public.predictions) vs Baseline
                     Current 15-min slot | 5-min auto-refresh          (public.baseline_profile), seeded by date
                          Missed Demand + Waste Summary                                    │
                     Reads public.predictions + live Neon stockout/waste                   ▼
                                                                                data/ab_results.json
                                                                                             │
                                                                                git commit + push
                                                                                             │
                                                                                [Astro Portfolio Site]
                                                                           Daily ML vs Baseline metrics display


  ── Manual retrain path (Snowflake resumed on demand, suspended otherwise) ──

  extract_to_snowflake.py → dbt run → ml.train / ml.predict → MARTS.PREDICTIONS
                                                                       │
                                                    export_predictions_to_neon.py
                                                                       │
                                                                       ▼
                                                          public.predictions (Neon)
                                                     [KS_WH suspended again after]
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Ingest API | FastAPI |
| POS Simulation | Python (async/httpx, Poisson arrivals, FIFO batch management) |
| Transactional DB | Neon (cloud Postgres) — per-store schemas, plus shared `public.predictions` / `public.baseline_profile` tables |
| Analytics Warehouse | Snowflake — suspended by default, resumed manually only for retraining (see decision #20) |
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
│       └── data_fetch.py      # get_production_plan(), get_waste_summary() — all reads
│                                # from Neon (public.predictions + live per-store tables)
│
├── scripts/
│   ├── init_db.py             # One-time Neon schema + table creation
│   ├── extract_to_snowflake.py # Incremental (per-store watermark on created_at): Neon → KS_DB.RAW
│   ├── run_pipeline.py        # Nightly cron: build_baseline_profile → A/B → git push (no Snowflake)
│   ├── build_baseline_profile.py # Neon-native port of dbt's int_sales__time_of_day_profile;
│   │                              # rebuilds public.baseline_profile from raw sales_events nightly
│   ├── export_predictions_to_neon.py # Snowflake MARTS.PREDICTIONS → Neon public.predictions;
│   │                              # run once and again after every manual retrain
│   ├── run_daily_simulation.py # A/B comparison — ML vs baseline, outputs data/ab_results.json
│   │                              # (reads public.predictions + public.baseline_profile from Neon)
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
- Live POS simulator — async/httpx, SimClock, StoreState FIFO inventory, slot-boundary production logic, cook times, batch sizes, RUSH_CURVE-scaled batch quantities, startup inventory seeding (rounded to a whole unit), 24-hour prediction reload (from Neon `public.predictions` as of 2026-07-25)
- Snowflake: `KS_DB`, `KS_WH`, `RAW.SALES_EVENTS`, `RAW.WASTE_LOG`, `RAW.STOCKOUT_EVENTS` — **suspended by default as of 2026-07-25**, resumed manually only for retraining (decision #20)
- Full dbt pipeline: staging → intermediate → marts (all models still defined and used during manual retrains; no longer run nightly)
- LightGBM model trained, predictions (12 stores × 45 active items × 672 slots, minus off-window slots filtered per item's `time_of_day`) written to `MARTS.PREDICTIONS` — retrain via `python -m ml.train` then `python -m ml.predict`, then `python scripts/export_predictions_to_neon.py` to push the refreshed table to Neon (see retrain playbook below; no wrapper script; `run_training.py` no longer exists)
- Cold-start fallback via `mart_cold_start_profile` (category-level averages by slot_index, threshold = 4 samples) — computed during manual retrains only
- Streamlit dashboard: split Kitchen/Chicken production queues, current 15-min slot (anchored to Neon's own clock via `get_sim_now()`, not wall-clock, since the sim clock can drift from real time), missed demand, waste summary (units sold + total sales + waste %), 5-min autorefresh, session state checkboxes with completed items table, deployed live at [kitchensync.streamlit.app](https://kitchensync.streamlit.app) (Streamlit Community Cloud). All dashboard reads — stockout/waste (live) and predictions — come from Neon as of 2026-07-25; no Snowflake dependency remains in `dashboard/utils/data_fetch.py`.
- A/B comparison system: `run_daily_simulation.py` — in-memory, seeded by date, ML vs hourly-average baseline, outputs `data/ab_results.json`; both prediction sources (`public.predictions`, `public.baseline_profile`) read from Neon
- AWS EC2 deployment: API + simulator as systemd services (auto-restart on crash/reboot)
- Nightly cron pipeline: single crontab line on EC2 (`crontab -l`), no separate systemd timer —
  ```
  0 2 * * * cd /home/ubuntu/kitchensync && git pull --rebase origin master && PYTHONPATH=. /home/ubuntu/.local/bin/uv run python scripts/run_pipeline.py >> logs/pipeline.log 2>&1
  ```
  which runs `build_baseline_profile.py` → A/B comparison → git push (no Snowflake step; retraining is a separate manual playbook, see below); commit step guards against "nothing to commit" so a no-op day doesn't fail the whole run. **Consolidated 2026-07-25**: the crontab previously had a commented-out `run_pipeline.py` line and a separate *active* line that called `run_daily_simulation.py` directly (bypassing `run_pipeline.py`, and — before the Neon migration — still querying Snowflake nightly even with `extract`/`dbt`/`predict` skipped). Both were replaced with the single line above.
- Portfolio site integration: `ab_results.json` committed to GitHub nightly, consumed by Astro static site
- Snowflake auth: RSA key pair (`~/.ssh/snowflake_rsa.p8`), registered via `ALTER USER` — still used for the manual retrain playbook
- Two production-logic bugs found and fixed (2026-07-01/02) — see design decisions #18 and #19 below
- Snowflake removed from the nightly/live hot path (2026-07-25) — see design decision #20 and the retrain playbook below

### Manual Retrain Playbook (Snowflake, on demand)

Snowflake stays suspended except when manually retraining the model:

1. Resume `KS_WH` in Snowflake (`ALTER WAREHOUSE KS_WH RESUME;` or via the Snowflake UI)
2. `PYTHONPATH=. uv run python scripts/extract_to_snowflake.py` — incremental watermark catches up all Neon activity since the last extract
3. `uv run dbt run --project-dir dbt` — rebuilds all marts, including `MART_ML_TRAINING_FEATURES`
4. `PYTHONPATH=. uv run python -m ml.train` then `PYTHONPATH=. uv run python -m ml.predict` — refreshes `MARTS.PREDICTIONS` in Snowflake
5. `PYTHONPATH=. uv run python scripts/export_predictions_to_neon.py` — pushes the new table to Neon, where the dashboard and A/B sim actually read from
6. `ALTER WAREHOUSE KS_WH SUSPEND;` — suspend again

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
- `START_TIME` — determined at startup by `get_start_time()`: queries `MAX(created_at)` across each Neon store schema's `sales_events` table directly (repointed from Snowflake `RAW.SALES_EVENTS` on 2026-07-25, since RAW no longer updates nightly) and resumes from the latest timestamp found; falls back to `datetime(2026, 7, 1, 0, 0, 0)` if Neon is empty (update this fallback whenever the historical seed window is regenerated with a new `START_DATE`)

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
- `refresh_targets_task()` — loads predictions from Neon `public.predictions` at startup and reloads every 24h (`asyncio.sleep(86400)`), not a one-time load. Repointed from Snowflake `MARTS.PREDICTIONS` on 2026-07-25.

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
12. **Retraining is manual** — cron runs `build_baseline_profile → A/B` nightly (Snowflake steps removed 2026-07-25, see decision #20) but never retrains the model. Retraining is triggered manually after significant data accumulation via the retrain playbook (`extract_to_snowflake.py` → `dbt run` → `ml.train` → `ml.predict` → `export_predictions_to_neon.py`, see Current State section). The model is committed to git (`ml/models/lgbm.joblib`) so EC2 can pull a new model without running training on the t3.micro (which OOMs)
13. **A/B baseline never writes to Neon** — baseline system is purely in-memory metrics; only ML system generates training data; prevents baseline behavior from corrupting the model's learning signal
14. **Honest A/B finding** — ML achieves +1.6pp better service level (97.6% vs 96.1%) and ~40% fewer stockout events, at the cost of +3.3pp more waste (8.6% vs 5.3%); root cause is the ML system's production checks firing ~4x more often (every 15-min slot boundary vs. baseline's hourly), each subject to the same `ceil()`-driven ~1-unit rounding tax described in decision #11 — not a batch floor (there isn't one); a production system would need a cost function to balance the trade-off
15. **Conditional mean bias fix (2026-06-13)** — `int_sales__time_of_day_profile` originally averaged only over days with non-zero sales, making `avg_slot_quantity` a conditional mean (E[X|X>0]) instead of the true expected demand. For low-traffic stores this inflated predictions 3–4x. Fixed by computing `SUM(quantity) / total_dates` where `total_dates` counts all observed days for that store/day_of_week, including zero-sale days.
16. **Simulator restart resume** *(query source superseded 2026-07-25, see decision #20)* — `get_start_time()` queries `MAX(created_at)` at startup and uses that as `START_TIME`, so the simulation clock resumes from the latest observed event rather than re-generating already-seen events. Originally queried Snowflake `RAW.SALES_EVENTS`; now queries Neon's per-store `sales_events` tables directly, since `RAW` no longer updates nightly. Falls back to a hardcoded date if empty — keep this fallback in sync with `START_DATE` in the historical generator whenever the seed window is regenerated.
17. **Snowflake RSA key path via env var** — `SNOWFLAKE_PRIVATE_KEY_PATH` defaults to `~/.ssh/snowflake_rsa.p8` if not set. Avoids hardcoding the EC2-specific absolute path and makes the Docker setup portable. Used in `ml/features.py` (SQLAlchemy engine) and `scripts/extract_to_snowflake.py` (connector).
18. **Production time-of-day gate must be OR, not AND (fixed 2026-07-02)** — `pos_simulator.py`'s per-item cook-decision skip check was written as `if (not item["active"] and item["added"] <= date and hour not in range(...)): continue`. Since `not item["active"]` is `False` for every real menu item, the whole `and`-chain collapsed to `False` and `continue` never fired — off-window items (e.g. chicken, available only 9am–10pm) got cook orders computed 24/7, with zero matching demand outside their window. This produced chronic overproduction concentrated at low-traffic stores (waste % inversely correlated with store traffic level: ~88% at level-1 stores vs. ~17% at level-4). Fixed to `if (not item["active"]) or (item["added"] > date) or (hour not in range(...)): continue` — an OR of the three skip-conditions, matching the (already-correct) positive filter used on the sales-generation side of the same file. `historical_generator.py` and `run_daily_simulation.py` were both already correct and unaffected.
19. **Startup-seeded inventory must be rounded (fixed 2026-07-02)** — `StoreState` startup seeding used the raw `predicted_units` sum from `MARTS.PREDICTIONS` directly as a batch `quantity`, without rounding. `predicted_units` is stored as an unrounded float; every other cook-quantity code path explicitly rounds (`int(np.ceil(gap))`), but this one didn't. Since `consume()` only subtracts whole-number sale quantities from a batch, the fractional remainder persisted through the batch's lifecycle and showed up as a fractional quantity in waste logs too, if the batch expired before selling out. Fixed with `seed_demand = round(seed_demand)`. Self-limiting even before the fix: seeding only runs once at simulator startup, so the fractional contamination fully flushes out (sold or wasted) within one `hold_time` window and never recurs.
20. **Snowflake removed from the nightly/live hot path (2026-07-25)** — cost-driven: Snowflake compute became unsustainable, and Neon was separately approaching its monthly compute-hour cap. The original idea (copy `MARTS.PREDICTIONS` to an EC2-local DB) didn't hold up: (a) the dashboard reads `MARTS.PREDICTIONS` directly too, not just the A/B script; (b) the A/B baseline needs `INT_SALES__TIME_OF_DAY_PROFILE` in addition to `PREDICTIONS`; (c) Streamlit Community Cloud cannot reach an EC2-local database without exposing a public port, so both tables had to land somewhere both the dashboard and EC2 can already reach — Neon. Landed as: `scripts/build_baseline_profile.py` ports the `int_sales__time_of_day_profile` SQL logic (including the decision #15 conditional-mean fix) to run directly against Neon's per-store schemas nightly, replacing dbt for that one model; `scripts/export_predictions_to_neon.py` does a one-time (and retrain-time) export of `MARTS.PREDICTIONS` into Neon `public.predictions`. `run_daily_simulation.py`, `dashboard/utils/data_fetch.py`, and `pos_simulator.py` (`get_start_time()`, `refresh_targets_task()`) were repointed from Snowflake to these two Neon tables. `run_pipeline.py`'s nightly chain simplified from `extract → dbt → predict → A/B → push` to `build_baseline_profile → A/B → push`. Snowflake itself is suspended (`ALTER WAREHOUSE KS_WH SUSPEND;`), not dropped, and is resumed only for the manual retrain playbook (see Current State section). Net effect: predictions and the baseline profile no longer freeze between retrains — the baseline keeps updating nightly from fresh Neon data, only the LightGBM model itself is static between manual retrains (unchanged from decision #12).
