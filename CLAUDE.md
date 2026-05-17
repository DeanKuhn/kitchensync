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
                               [dbt Core pipeline]
                                        │
                                        ▼
                              [Snowflake Data Warehouse]
                         stg_ → intermediate_ → mart_ → metrics_
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
| Language | Python 3.11+ |
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
| Containerization | Dockerfile (reference only — not used in dev) |
| Dev environment | VS Code + Claude Code |

---

## Repository Structure

```
kps-forecasting/
├── CLAUDE.md                  # This file
├── README.md                  # Public-facing project documentation
├── Dockerfile                 # Reference only — not used in active dev
├── .env.example               # Environment variable template
├── requirements.txt
├── pyproject.toml             # Optional: project metadata
│
├── config/
│   ├── menu.yaml              # Food items, categories, active/inactive flags
│   └── stores.yaml            # Store IDs, names, region metadata
│
├── data/
│   ├── seeds/                 # dbt seed CSV files (historical baseline)
│   └── exports/               # Parquet feature exports for ML
│
├── simulator/
│   ├── __init__.py
│   ├── pos_simulator.py       # Fires fake POS events to the ingest API
│   └── historical_generator.py # Generates synthetic historical dataset
│
├── api/
│   ├── __init__.py
│   ├── main.py                # FastAPI app entry point
│   ├── routes/
│   │   └── sales.py           # POST /sale endpoint
│   ├── models/
│   │   └── schemas.py         # Pydantic models for sale events
│   └── db/
│       └── connection.py      # Neon/Postgres connection management
│
├── dbt/
│   ├── dbt_project.yaml
│   ├── profiles.yaml.example
│   ├── seeds/                 # Historical data loaded into Snowflake
│   ├── models/
│   │   ├── staging/           # stg_sales__*, stg_stores__*, stg_menu__*
│   │   ├── intermediate/      # int_sales_hourly_*, int_rolling_features_*
│   │   ├── marts/             # mart_store_sales, mart_item_velocity
│   │   └── metrics/           # metrics_forecast_accuracy, metrics_stockout_rate
│   ├── tests/
│   └── macros/
│
├── ml/
│   ├── __init__.py
│   ├── features.py            # Feature engineering from mart/intermediate models
│   ├── train.py               # Training pipeline (baseline + LightGBM)
│   ├── predict.py             # Inference: produces next-hour production plan
│   ├── evaluate.py            # MAE, RMSE, urgency precision/recall
│   └── models/                # Serialized model artifacts (.pkl / .joblib)
│
├── dashboard/
│   ├── app.py                 # Streamlit entrypoint
│   ├── components/
│   │   ├── production_plan.py # Per-store production plan table
│   │   └── store_selector.py  # Store dropdown
│   └── utils/
│       └── data_fetch.py      # Pulls latest predictions from Snowflake/Postgres
├── scripts/
│   └── init_db.py             # One-time setup script
│
└── tests/
    ├── test_api.py
    ├── test_simulator.py
    └── test_ml_features.py
```

---

## Database Design

### Neon (Postgres) — Transactional Layer

Each store gets its own schema: `store_001`, `store_002`, ... `store_015`

Within each schema:

```sql
-- sales_events: raw POS events written in real-time
CREATE TABLE {store_schema}.sales_events (
    id            SERIAL PRIMARY KEY,
    store_id      TEXT NOT NULL,
    item_id       TEXT NOT NULL,
    quantity      INTEGER NOT NULL,
    sale_ts       TIMESTAMPTZ NOT NULL DEFAULT now(),
    register_id   TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

A shared `public` schema holds reference tables:

```sql
-- stores reference table
CREATE TABLE public.stores (
    store_id    TEXT PRIMARY KEY,
    store_name  TEXT,
    region      TEXT,
    active      BOOLEAN DEFAULT TRUE
);

-- menu items reference table
CREATE TABLE public.menu_items (
    item_id     TEXT PRIMARY KEY,
    item_name   TEXT,
    category    TEXT,   -- 'sandwich', 'pizza', 'hot_food', etc.
    active      BOOLEAN DEFAULT TRUE,
    added_at    DATE,
    removed_at  DATE
);
```

### Snowflake — Analytics Layer

Database: `KPS_DB`
Schemas: `RAW`, `STAGING`, `INTERMEDIATE`, `MARTS`, `METRICS`

dbt writes to `STAGING` through `METRICS`. Raw data is synced from Neon via a lightweight Python sync job (or direct Snowflake connector).

---

## dbt Layer Design

### Staging (`stg_`)
- `stg_sales__events` — cleaned, typed sales events
- `stg_stores__dim` — store dimension
- `stg_menu__items` — menu dimension with active flag

### Intermediate (`int_`)
- `int_sales__hourly_by_store_item` — sales aggregated by store + item + hour
- `int_sales__rolling_features` — 30-min, 1hr, 4hr rolling sums per item per store
- `int_sales__time_of_day_profile` — historical avg demand by hour/dow per item

### Marts (`mart_`)
- `mart_store_sales` — wide fact table: store + item + time features + rolling aggregates
- `mart_item_velocity` — current sell-through rate vs. historical baseline

### Metrics (`metrics_`)
- `metrics_forecast_accuracy` — predicted vs. actual units (MAE, RMSE per item)
- `metrics_stockout_rate` — how often urgent flag was triggered, and was it justified

---

## Menu Configuration

Defined in `config/menu.yaml`. Example structure:

```yaml
items:
  - id: "HOT_DOG_REG"
    name: "Regular Hot Dog"
    category: "roller_grill"
    active: true
    added: "2023-01-01"

  - id: "PIZZA_SLICE_CHEESE"
    name: "Cheese Pizza Slice"
    category: "pizza"
    active: true
    added: "2023-01-01"

  - id: "BRAT_CHEDDAR"
    name: "Cheddar Brat"
    category: "roller_grill"
    active: false
    removed: "2024-06-01"
```

Items with `active: false` are excluded from forecasting. New items with no history get a **cold-start fallback** — the model uses category-level averages until 7 days of data accumulates.

---

## ML Model Design

### Input Features
| Feature | Source |
|---|---|
| `hour_of_day` | Derived from sale timestamp |
| `day_of_week` | Derived from sale timestamp |
| `is_weekend` | Derived |
| `rolling_30min_units` | `int_sales__rolling_features` |
| `rolling_1hr_units` | `int_sales__rolling_features` |
| `rolling_4hr_units` | `int_sales__rolling_features` |
| `avg_units_this_hour_dow` | `int_sales__time_of_day_profile` (historical) |
| `store_id` (encoded) | Store dimension |
| `item_id` (encoded) | Menu dimension |
| `days_since_item_added` | New item cold-start feature |

### Output
- `predicted_units_next_1hr` — float, rounded to nearest integer for display
- `urgency_flag` — `NORMAL` or `URGENT`

**Urgency logic:** If current rolling sell-through rate exceeds the historical average for this hour by a configurable threshold (default: 1.4x), flag as `URGENT`.

### Training
1. Generate 12+ months of synthetic historical data via `historical_generator.py`
2. Train baseline (scikit-learn RandomForest) — log metrics, serialize model
3. Train LightGBM — log metrics, compare vs. baseline, serialize model
4. Models are stored in `ml/models/` as `.joblib` files

### Inference Cycle
- Runs every 5 minutes via a scheduler (APScheduler or a simple cron loop)
- Pulls latest rolling features from Snowflake (or Neon if Snowflake sync lags)
- Produces a production plan per store
- Writes results to a `predictions` table in Snowflake for the dashboard to consume

---

## Store Configuration

Defined in `config/stores.yaml`. 10–15 stores. Example:

```yaml
stores:
  - id: "store_001"
    name: "Madison East"
    region: "South Wisconsin"
    active: true

  - id: "store_002"
    name: "Eau Claire North"
    region: "West Wisconsin"
    active: true
```

Each store gets its own Postgres schema and is treated as an independent forecasting unit — demonstrating horizontal scalability.

---

## Streamlit Dashboard

**Purpose:** Show results, not impress visually. Functionality over form.

**Views:**
1. **Store selector** — dropdown to choose active store
2. **Production Plan table** — refreshes every 5 minutes
   - Columns: Item Name | Category | Predicted Units (Next 1hr) | Status
   - Status is color-coded: green = NORMAL, red = URGENT
3. **Rolling Sales chart** — simple line chart of last 2 hours per item (optional)

Dashboard reads from Snowflake `predictions` table and `mart_store_sales`.

---

## Stretch Goals (Scoped, Not Guaranteed)

| Goal | Status | Notes |
|---|---|---|
| Weather API feature | Stretch | Open-Meteo (free, no key needed) — add `temp_f` and `precip_mm` as model features |
| Model retraining pipeline | Stretch | Weekly cron job re-trains on last 90 days of data, replaces model artifact if RMSE improves |
| Docker containerization | Reference only | `Dockerfile` exists in repo root for reference; not used in active development |

---

## Environment Variables

See `.env.example`. Required vars:

```
# Neon (Postgres)
NEON_DATABASE_URL=postgresql://user:pass@host/dbname

# Snowflake
SNOWFLAKE_ACCOUNT=
SNOWFLAKE_USER=
SNOWFLAKE_PASSWORD=
SNOWFLAKE_DATABASE=KPS_DB
SNOWFLAKE_WAREHOUSE=
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

### Phase 1 — Foundation
- [ ] Repo structure scaffolded
- [ ] `config/menu.yaml` and `config/stores.yaml` created
- [ ] Neon database provisioned, schemas created per store
- [ ] FastAPI ingest API running locally, writing to Neon
- [ ] POS simulator firing realistic events

### Phase 2 — Data Pipeline
- [ ] Historical data generator producing 12 months of synthetic data
- [ ] Snowflake database and schemas provisioned
- [ ] dbt project initialized, connected to Snowflake
- [ ] Staging models complete and tested
- [ ] Intermediate models complete (rolling features, time-of-day profiles)
- [ ] Mart models complete
- [ ] Metrics models stubbed

### Phase 3 — ML Model
- [ ] Feature engineering script pulling from Snowflake marts
- [ ] Baseline model trained and evaluated
- [ ] LightGBM model trained, compared to baseline
- [ ] Cold-start logic implemented for new menu items
- [ ] Urgency flag logic implemented and tested
- [ ] Inference loop running on 5-minute schedule

### Phase 4 — Dashboard
- [ ] Streamlit app skeleton
- [ ] Store selector wired to live data
- [ ] Production plan table rendering with NORMAL/URGENT status
- [ ] 5-minute auto-refresh working

### Phase 5 — Polish & Stretch
- [ ] README finalized with architecture diagram
- [ ] dbt metrics layer complete
- [ ] Model retraining pipeline (stretch)
- [ ] Weather feature integration (stretch)
- [ ] Dockerfile present and documented

---

## Key Design Decisions

1. **Per-store Postgres schemas over separate databases** — simpler connection management, still demonstrates schema-level isolation
2. **FastAPI over direct DB writes from simulator** — demonstrates API-first design, more realistic to actual POS integrations
3. **LightGBM over Prophet** — allows feature engineering showcase; Prophet is a black box for interviews
4. **dbt Core (not Cloud)** — keeps it local/free, which is realistic for a dev environment
5. **Config-file-driven menu** — mirrors real-world pattern where items can be toggled without code changes; cold-start logic handles new items gracefully
6. **Snowflake as analytics layer** — separates concerns between transactional and analytical workloads; Neon handles writes, Snowflake handles reads for ML and dashboard

---

## Commands Reference

```bash
# Start the ingest API
uvicorn api.main:app --reload --port 8000

# Run the POS simulator
python simulator/pos_simulator.py

# Generate historical data
python simulator/historical_generator.py

# Run dbt transformations
cd dbt && dbt run

# Run dbt tests
cd dbt && dbt test

# Train models
python ml/train.py

# Run inference (one cycle)
python ml/predict.py --store store_001

# Launch dashboard
streamlit run dashboard/app.py
```