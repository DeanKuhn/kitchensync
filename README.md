# KitchenSync

A portfolio-grade simulation of a Kwik Trip-style Kitchen Production System (KPS). KitchenSync ingests real-time simulated POS events, transforms them through a dbt + Snowflake analytics pipeline, and feeds a LightGBM forecasting model that produces per-store, per-item food production plans at 15-minute slot grain. A Streamlit dashboard surfaces the results for kitchen staff — split into separate Kitchen and Chicken production queues, refreshed every 5 minutes.

An A/B comparison pipeline runs nightly on AWS EC2, pitting the ML system against a naive hourly-average baseline. Results are written to `data/ab_results.json`, committed to GitHub, and consumed by a static Astro portfolio site that updates automatically each morning.

Built by someone who works with the real system daily.

---

## What This Demonstrates

- **End-to-end data engineering** — async POS event ingestion → Postgres → Snowflake → dbt → ML → live dashboard
- **Deliberate architectural tradeoffs** — per-store schema isolation in Neon for transactional writes; consolidated single-table design in Snowflake for cross-store analytics and model training
- **Production-grade dbt pipeline** — staging → intermediate → mart layers with clean schema separation, `QUALIFY` window patterns for per-store snapshots, and a custom `generate_schema_name` macro
- **ML feature engineering** — 15-minute slot grain demand profiles across 672 weekly slots per store/item; cold-start handling for new menu items via category-level fallback
- **Realistic simulator design** — Poisson arrivals, FIFO batch inventory, slot-boundary production logic, cook times, RUSH_CURVE-scaled batch sizes, and startup inventory seeding
- **Honest A/B evaluation** — ML vs. hourly-average baseline comparison with a real trade-off finding, not a cherry-picked result

---

## System Architecture

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
| Transformations | dbt Core |
| ML — Baseline | scikit-learn (RandomForest) |
| ML — Production | LightGBM |
| Dashboard | Streamlit + streamlit-autorefresh |
| A/B Comparison | Pure Python in-memory simulation |
| Portfolio Site | Static Astro site, fed by ab_results.json |
| Cloud Hosting | AWS EC2 (systemd services + cron) |
| Data formats | CSV (seed data), JSON (A/B results) |
| Config | YAML (menu items, store definitions) |
| Package Management | uv |
| Auth | Snowflake RSA key pair (~/.ssh/snowflake_rsa.p8) |

---

## How It Works

### 1. POS Simulation

An async Python simulator fires fake point-of-sale events to the ingest API using Poisson-distributed customer arrivals shaped by a per-hour `RUSH_CURVE`. Each store runs as an independent async task.

A `StoreState` class tracks FIFO batch inventory per item. Production decisions fire **once per 15-minute slot boundary** — not every tick. The look-ahead window equals the item's hold time, so the kitchen always cooks enough to cover the full shelf life. Cook quantities are scaled by `RUSH_CURVE[hour]` to prevent over-production at 3am and under-production at noon. On startup, inventory is pre-seeded from the current slot's predictions so the kitchen starts with realistic stock rather than empty shelves.

### 2. Ingest API

A FastAPI application receives live events and writes them to the appropriate store schema in Neon. Each of the 12 stores has its own Postgres schema (`store_012`, `store_027`, etc.) — isolating transactional writes at the schema level and demonstrating a realistic multi-tenant database pattern.

### 3. Snowflake Extract

`scripts/extract_to_snowflake.py` pulls all sales, waste, and stockout events from all 12 Neon schemas and loads them into `KS_DB.RAW` in Snowflake as single consolidated tables with a `store_id` column. This is an intentional design contrast: per-store isolation for writes, unified table for analytics.

### 4. dbt Pipeline

dbt Core transforms raw events through three layers:

- **Staging** — cleans and types raw events; derives `sale_date`, `sale_hour`, `sale_minute`, `day_of_week`, and `slot_index` (15-min grain, 0–671)
- **Intermediate** — `int_sales__rolling_features_15min` aggregates sales to slot buckets; `int_sales__time_of_day_profile` builds historical average demand per store + item + slot across the full 672-slot weekly cycle
- **Marts** — business logic layer: `mart_store_sales_15min` (wide fact table, per-store QUALIFY pattern), `mart_cold_start_profile` (category-level slot averages), `mart_waste_percentage` (monetary waste formula with units sold), `mart_stockout_summary` (missed demand by hour)

All mart models use `QUALIFY ROW_NUMBER() OVER (PARTITION BY store_id, item_id ORDER BY ...)` for per-store snapshots — never a global `LIMIT 1`, which would silently return only the most-advanced store.

### 5. ML Forecasting

A LightGBM model predicts units to produce per store, per item, per 15-minute slot. Features are sourced from `int_sales__time_of_day_profile` and include `slot_index`, `sale_hour`, `sale_minute`, `day_of_week`, `is_weekend`, `avg_slot_quantity`, and label-encoded `store_id` / `item_id`.

Inference produces **190,773 predictions** covering all 672 slots × 12 stores × 42 active items — a complete weekly production profile. Items with fewer than 4 historical data points fall back to category-level averages from `mart_cold_start_profile`.

### 6. Streamlit Dashboard

The dashboard queries `MARTS.PREDICTIONS` for the current 15-minute slot (computed from wall-clock time) and displays two separate production queues matching the real KPS layout:

- **[Kitchen]** — sandwiches, sides, roller grill items
- **[Chicken]** — chicken pieces and appetizers

Each table shows predicted units and missed demand (units lost to stockouts). Kitchen staff can check off completed batches — done items move to a completed table and are removed from the active queue. Session state persists checkboxes across the 5-minute auto-refresh. A waste summary below shows units sold, total sales revenue, and waste percentage per category group (Hot Foods / Roller Grill / Chicken).

### 7. A/B Comparison

`scripts/run_daily_simulation.py` runs two parallel in-memory simulations against identical seeded Poisson demand — no API calls, no database writes:

- **ML system** — reads `MARTS.PREDICTIONS` (LightGBM, 15-min grain); production fires every slot boundary (96 checks/day); look-ahead = `hold_time * 4` slots
- **Baseline system** — reads `INT_SALES__TIME_OF_DAY_PROFILE` aggregated to hourly grain; production fires at hour boundaries (24 checks/day); look-ahead = `hold_time` hours

Results are appended to `data/ab_results.json` (daily + cumulative metrics). The nightly cron job runs this after retraining, then commits and pushes the JSON to GitHub. A GitHub Actions workflow triggers the Astro portfolio site to rebuild with fresh numbers.

> **Honest finding:** The ML system reduces stockouts by ~31% vs. the baseline but increases waste by ~5.5 percentage points. Two causes: 4× more production checks means 4× more minimum-batch cook opportunities, and the LightGBM model slightly overpredicts. A production system would need a cost function weighing stockout revenue loss against waste cost to optimize the trade-off — the framework surfaces the real tension.

---

## Key Design Decisions

**Per-store Postgres schemas vs. consolidated Snowflake table**
Each store gets its own schema in Neon (`search_path` scopes all queries automatically), but all stores share a single table in Snowflake with a `store_id` column. The transactional layer is optimized for isolated writes; the analytics layer is optimized for cross-store queries and model training. Same data, two different structures, two different jobs.

**15-minute slot grain for ML**
Rather than predicting hourly demand, the model operates at 15-minute resolution — 96 slots per day, 672 per week. This matches the real KPS planning cycle and allows the simulator's slot-boundary production logic to consume predictions directly without any aggregation step.

**Slot-boundary production logic**
Cook decisions fire once per slot change, not every simulator tick. The look-ahead window is `hold_time * 4` slots — the kitchen cooks enough to cover the item's full shelf life. This mirrors how real kitchen staff think: cook for the window, not the moment.

**No retraining during simulation**
`MARTS.PREDICTIONS` is a static weekly profile loaded once at simulator startup. The background pipeline (running every 5 minutes) runs extract + dbt only — never predict or train. Replacing the predictions table mid-simulation would corrupt the production logic and destabilize the dashboard.

**Baseline never writes to Neon**
The A/B baseline is purely in-memory. Only the ML system generates training data. Allowing baseline behavior to write to Neon would corrupt the model's learning signal over time.

**LightGBM over Prophet**
Prophet is a black box for interviews. LightGBM allows explicit feature engineering that can be explained and defended — time-of-day profiles, cold-start fallbacks, label encoding choices — all of which are meaningful talking points.

---

## Project Structure

```
kitchensync/
├── config/
│   ├── menu.yaml              # Items: id, category, hold_time, cook_time, batch_size, popularity
│   └── stores.yaml            # 12 stores, 4 regions, traffic levels 1–4
├── data/
│   └── ab_results.json        # Nightly A/B comparison output (read by portfolio site)
├── simulator/
│   ├── pos_simulator.py       # Live async simulator
│   └── historical_generator.py # 42-day historical data generator
├── api/
│   ├── routes/events.py       # POST /sales, /waste, /stockout
│   ├── models/schemas.py      # Pydantic event models
│   └── db/connection.py       # Neon connection pool, per-store search_path
├── dbt/
│   ├── macros/                # generate_schema_name.sql
│   └── models/
│       ├── staging/           # stg_sales_events, stg_waste_log, stg_stockout_events
│       ├── intermediate/      # int_sales__rolling_features_15min, int_sales__time_of_day_profile
│       └── marts/             # mart_store_sales_15min, mart_cold_start_profile,
│                              # mart_waste_percentage, mart_stockout_summary,
│                              # mart_ml_training_features
├── ml/
│   ├── features.py            # FEATURE_COLS, Snowflake engine
│   ├── train.py               # LightGBM training
│   └── predict.py             # Inference → MARTS.PREDICTIONS (190,773 rows)
├── dashboard/
│   ├── app.py                 # Streamlit entry point
│   ├── components/            # production_plan.py, waste_summary.py, store_selector.py
│   └── utils/data_fetch.py    # get_production_plan(), get_waste_summary()
└── scripts/
    ├── init_db.py             # One-time Neon schema creation
    ├── extract_to_snowflake.py
    ├── run_prediction_update.py  # extract + dbt (runs every 5 min during simulation)
    ├── run_training.py           # full pipeline including train (run manually)
    └── run_daily_simulation.py   # A/B comparison — ML vs baseline, outputs ab_results.json
```

---

## Setup

### Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) — `pip install uv`
- Neon account (free tier sufficient)
- Snowflake account (free trial sufficient)

### Environment Variables

```bash
cp .env.example .env
```

Fill in Neon, Snowflake, API, and simulator credentials. See `.env.example` for all required fields.

### Install Dependencies

```bash
uv sync
```

### Snowflake Authentication

This project uses RSA key pair authentication for Snowflake (no passwords). Generate a key pair and register the public key:

```bash
# Generate private key
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out ~/.ssh/snowflake_rsa.p8 -nocrypt

# Extract public key
openssl rsa -in ~/.ssh/snowflake_rsa.p8 -pubout -out ~/.ssh/snowflake_rsa.pub
```

Then register the public key in Snowflake:
```sql
ALTER USER <your_user> SET RSA_PUBLIC_KEY='<contents of snowflake_rsa.pub, header/footer removed>';
```

Update `~/.dbt/profiles.yml` to use `private_key_path: ~/.ssh/snowflake_rsa.p8` instead of a password.

### First-Time Setup

```bash
# 1. Initialize Neon schemas (one time only)
PYTHONPATH=. uv run python scripts/init_db.py

# 2. Generate 42 days of historical data (Jan 1 – Feb 11, 2026)
PYTHONPATH=. uv run python -m simulator.historical_generator

# 3. Upload menu seed data to Snowflake
uv run dbt seed --project-dir dbt

# 4. Run the full pipeline (extract → dbt → train → predict)
PYTHONPATH=. uv run python -m scripts.run_training
```

### Running the System

```bash
# Terminal 1 — Ingest API
PYTHONPATH=. uv run uvicorn api.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — Streamlit dashboard
PYTHONPATH=. uv run streamlit run dashboard/app.py

# Terminal 3 — Live POS simulator
PYTHONPATH=. uv run python -m simulator.pos_simulator
```

### Running the A/B Comparison

```bash
PYTHONPATH=. uv run python scripts/run_daily_simulation.py
```

Results are written to `data/ab_results.json`. Run this after `run_training.py` for fresh predictions.

---

## AWS Deployment

The live system runs on AWS EC2:

- **API** and **simulator** run as systemd services (auto-restart on crash or reboot)
- **Nightly cron (2am UTC):** extract → dbt → retrain → predict → A/B comparison → git push
- **GitHub Actions** triggers the Astro portfolio site to rebuild after each push of `ab_results.json`

Systemd service files are in `deploy/` (not committed — contain credentials).

---

## Store & Menu Configuration

**12 stores** across 4 Midwest regions (West Wisconsin, South Wisconsin, Minnesota, Iowa). Traffic levels 1–4 control simulated sales volume.

**42 active menu items** across 5 categories: `sandwich`, `side`, `roller_grill`, `chicken`, `appetizer`. Items map to two dashboard production queues:
- **Kitchen** — sandwich + side + roller_grill
- **Chicken** — chicken + appetizer

New items added to `config/menu.yaml` are automatically handled by the cold-start fallback until sufficient sales history accumulates (threshold: 4 data points). Set `active: false` to retire an item without touching any code.

---

## Simulated Timeline

| Period | Data |
|---|---|
| Jan 1 – Feb 11, 2026 | 42 days of synthetic historical data (~2.7M events) |
| Feb 12, 2026 onward | Live simulation |

Cold-start items (added Feb 12): `CHIMI`, `BUFFALO_CHICKEN_ROLLERBITES`, `JALAPENO_BITES`
