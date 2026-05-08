# KPS Food Forecasting System

A portfolio project simulating a Kwik Trip-style Kitchen Production System (KPS). The system uses a real-time data pipeline, a multi-store Postgres architecture, a dbt-powered Snowflake analytics warehouse, and a LightGBM forecasting model to produce per-store food production plans — refreshed every 5 minutes.

---

## What This Project Demonstrates

- **Robust data pipeline engineering** — real-time POS event ingestion via FastAPI, per-store schema isolation in Neon (Postgres), and a sync pipeline into Snowflake
- **Modern analytics stack** — dbt Core transformations across staging → intermediate → mart → metrics layers
- **ML model development** — baseline scikit-learn model vs. production LightGBM, feature engineering from time-series sales data, cold-start handling for new menu items
- **Scalable architecture** — 10–15 simulated stores, each treated as an independent forecasting unit; config-file-driven menu allows items to be toggled without code changes
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
| POS Simulation | Python (randomized, time-aware traffic patterns) |
| Transactional DB | Neon (cloud Postgres) |
| Analytics Warehouse | Snowflake |
| Transformations | dbt Core |
| ML — Baseline | scikit-learn (RandomForest) |
| ML — Production | LightGBM |
| Dashboard | Streamlit |
| Config | YAML (menu items, store definitions) |

---

## How It Works

### 1. POS Simulation
A Python simulator fires fake point-of-sale events to a FastAPI endpoint at randomized intervals, mimicking realistic store traffic — busy at lunch, slow overnight, weekend spikes. Each event carries a store ID, item ID, quantity, and timestamp.

### 2. Ingest API
A FastAPI application receives sale events and writes them to the appropriate store schema in Neon (Postgres). Each of the 10–15 stores has its own schema (`store_001`, `store_002`, etc.), demonstrating horizontal schema isolation.

### 3. dbt Pipeline
dbt Core transforms raw sales events through four layers in Snowflake:
- **Staging** — cleans and types raw events
- **Intermediate** — computes rolling 30-min, 1hr, and 4hr sales aggregates; builds time-of-day demand profiles
- **Marts** — wide fact tables combining store, item, time features, and rolling aggregates
- **Metrics** — forecast accuracy (MAE, RMSE) and stockout rate tracking

### 4. ML Forecasting Model
A LightGBM model trained on 12+ months of synthetic historical data predicts **units to produce in the next 1 hour** per item per store. Features include time-of-day, day-of-week, rolling sales windows, and historical demand profiles.

Items are flagged:
- `NORMAL` — predicted demand is in line with historical patterns
- `URGENT` — current sell-through rate exceeds historical average by 1.4x or more (configurable)

New menu items with no history fall back to category-level averages until 7 days of data accumulates.

### 5. Streamlit Dashboard
A simple dashboard refreshes every 5 minutes showing the current production plan per store. Kitchen staff see a table of items with predicted units and urgency status.

---

## Project Structure

```
kps-forecasting/
├── config/                    # menu.yaml, stores.yaml
├── data/                      # Seed CSVs, parquet exports
├── simulator/                 # POS event simulator, historical data generator
├── api/                       # FastAPI ingest service
├── dbt/                       # dbt project (staging → intermediate → marts → metrics)
├── ml/                        # Feature engineering, training, inference, evaluation
├── dashboard/                 # Streamlit app
├── scripts/                   # Random tasks
└── tests/                     # Unit tests for API, simulator, ML features
```

---

## Setup

### Prerequisites
- Python 3.11+
- Neon account (free tier sufficient)
- Snowflake account (free trial sufficient)
- dbt Core installed (`pip install dbt-snowflake`)

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
SNOWFLAKE_DATABASE=KPS_DB
SNOWFLAKE_WAREHOUSE=
SNOWFLAKE_ROLE=
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the System

```bash
# 1. Start the ingest API
uvicorn api.main:app --reload --port 8000

# 2. Start the POS simulator (separate terminal)
python simulator/pos_simulator.py

# 3. Run dbt transformations
cd dbt && dbt run

# 4. Train the forecasting model
python ml/train.py

# 5. Launch the dashboard
streamlit run dashboard/app.py
```

---

## Menu Configuration

Items are defined in `config/menu.yaml`. To add a new item:

```yaml
- id: "PRETZEL_CHEDDAR"
  name: "Cheddar Pretzel"
  category: "bakery"
  active: true
  added: "2025-01-01"
```

To retire an item:
```yaml
- id: "BRAT_CHEDDAR"
  name: "Cheddar Brat"
  category: "roller_grill"
  active: false
  removed: "2024-06-01"
```

Inactive items are excluded from forecasting automatically.

---

## Build Status

### Phase 1 — Foundation
- [ ] Repo scaffolded
- [ ] Config files (menu, stores)
- [ ] Neon provisioned, per-store schemas created
- [ ] FastAPI ingest API
- [ ] POS simulator

### Phase 2 — Data Pipeline
- [ ] Historical data generator
- [ ] Snowflake provisioned
- [ ] dbt staging models
- [ ] dbt intermediate models (rolling features, time-of-day profiles)
- [ ] dbt mart models
- [ ] dbt metrics models

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

---

## Disclaimer

This project is a personal portfolio simulation and is not affiliated with or endorsed by Kwik Trip, Inc. All store data, sales events, and food items are entirely synthetic.