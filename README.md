# KitchenSync

A portfolio-grade simulation of a Kwik Trip-style Kitchen Production System (KPS). KitchenSync ingests real-time simulated POS events into a Postgres (Neon) transactional layer and feeds a LightGBM forecasting model that produces per-store, per-item food production plans at 15-minute slot grain. A Streamlit dashboard surfaces the results for kitchen staff — split into separate Kitchen and Chicken production queues, refreshed every 5 minutes.

An A/B comparison pipeline runs nightly on AWS EC2, pitting the ML system against a naive hourly-average baseline, with a synthetic weather feature giving the ML side a structural edge the baseline's date-blind lookup structurally can't have. Results are written to `data/ab_results_v2.json`, committed to GitHub, and consumed by a static Astro portfolio site that updates automatically each morning.

Built by someone who works with the real system daily.

---

## What This Demonstrates

- **End-to-end data engineering** — async POS event ingestion → Postgres (Neon) → nightly feature rebuild → ML → live dashboard, entirely on a cost-conscious footprint
- **Feature engineering with a controlled natural experiment** — a synthetic `(temp_f, precip)` weather axis is fed to the ML model but is structurally invisible to the baseline's `(store, item, day_of_week, slot_index)` lookup, isolating exactly how much a model can exploit a signal a simpler system can't use
- **Realistic simulator design** — Poisson arrivals, FIFO batch inventory, slot-boundary production logic, cook times, and startup inventory seeding
- **Honest A/B evaluation, including where ML loses** — the writeup below reports a case where the baseline beats the model, not just the cases where it wins
- **A migrated, right-sized architecture** — originally a Neon + Snowflake + dbt stack; Snowflake was retired entirely once its usage no longer justified its cost, with dbt kept in the repo as a portfolio-only artifact rather than deleted outright

---

## System Architecture

```
[POS Simulator — EC2 systemd]
   buffers sales/waste/stockout in memory; every 5 min, opens one
   short-lived connection per store and bulk-inserts
                                                              │
                                                              ▼
                                                     [Neon (Postgres)]
                                                     Per-store schemas
                                              + shared public.predictions
                                              + shared public.baseline_profile
                                                              │
                                              [Nightly cron — 2am UTC]
                                          scripts/build_baseline_profile.py
                                    (ports dbt's time_of_day_profile logic to Neon SQL)
                                                              │
                                          ┌───────────────────┴───────────────────┐
                                          ▼                                       ▼
                              [Streamlit Dashboard]                  [A/B Comparison — run_daily_simulation.py]
                     Split Kitchen / Chicken production queues        ML (public.predictions) vs Baseline
                     Current 15-min slot | 5-min auto-refresh          (public.baseline_profile), seeded by date
                          Missed Demand + Waste Summary                                    │
                     Reads public.predictions + live Neon stockout/waste                   ▼
                                                                                data/ab_results_v2.json
                                                                                             │
                                                                                git commit + push
                                                                                             │
                                                                                [Astro Portfolio Site]
                                                                           Daily ML vs Baseline metrics display


  ── Manual retrain path (Neon only, no Snowflake) ──

  scripts/build_training_features.py (in-memory) → ml.train → ml.predict
                                                                       │
                                                                       ▼
                                                          public.predictions (Neon)
```

Everything in the live path — ingestion, training, inference, the dashboard, the A/B pipeline — runs against Neon. A dbt project (staging → intermediate → marts) remains in the repo as a portfolio-only artifact demonstrating a transformation-layer approach; it no longer touches live data. See `dbt/README.md` for the model-to-Neon-script mapping.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| POS Simulation | Python (asyncio, Poisson arrivals, FIFO batch management); writes directly to Neon in 5-min batches, no ingest API |
| Transactional DB | Neon (cloud Postgres) — per-store schemas + shared prediction/baseline/weather tables |
| Analytics Warehouse | ~~Snowflake~~ retired; dbt kept as a portfolio-only artifact |
| ML — Baseline | Hourly average (in-memory, no model) |
| ML — Production | LightGBM |
| Dashboard | Streamlit + streamlit-autorefresh |
| A/B Comparison | Pure Python in-memory simulation |
| Portfolio Site | Static Astro site, fed by `ab_results_v2.json` |
| Cloud Hosting | AWS EC2 (systemd services + cron) |
| Config | YAML (menu items, store definitions) |
| Package Management | uv |

---

## How It Works

### 1. POS Simulation

An async Python simulator generates fake point-of-sale events using Poisson-distributed customer arrivals shaped by a per-hour `RUSH_CURVE`, with daily volume and per-item popularity further shaped by that day's synthetic weather. Each store runs as an independent async task. Sales, waste, and stockout events are buffered in memory rather than written immediately; every 5 minutes, a background task flushes each store's buffer to its Neon schema in one bulk `execute_values` insert over a short-lived connection, then closes it. There's no ingest API in the live path anymore — an earlier version POSTed each event individually to a FastAPI service, but that service held a Postgres connection pool open for its entire process lifetime, which kept Neon's compute endpoint permanently awake and blew through the free tier's monthly compute-hour budget in about a week regardless of actual traffic. Batching lets Neon autosuspend between flushes instead.

On startup, the simulator queries Neon for the most recent `created_at` across all 12 store schemas and resumes the simulation clock from that timestamp, so a service restart picks up where the timeline left off. If Neon is empty, it falls back to a hardcoded date kept in sync with the historical generator's `START_DATE`.

A `StoreState` class tracks FIFO batch inventory per item. Production decisions fire **once per 15-minute slot boundary**, not every tick, and only for items currently active, released, and inside their `time_of_day` window — an OR of those three conditions gates the cook decision (an earlier AND-based version silently cooked off-window items around the clock, see design decisions below). The look-ahead window equals the item's hold time, so the kitchen cooks enough to cover the full shelf life, with no minimum-batch floor — quantities are rounded up, never padded. On startup, inventory is pre-seeded from the current slot's predictions, rounded to a whole unit, so the kitchen starts with realistic stock rather than empty shelves.

### 2. Nightly Feature Rebuild

`scripts/build_baseline_profile.py` rebuilds `public.baseline_profile` directly from raw Neon `sales_events` every night — a Neon-native port of what used to be a dbt model against Snowflake. Companion scripts (`build_cold_start_profile.py`, `build_traffic_ratio.py`, `build_training_features.py`) cover the rest of the feature set the same way. None of them touch Snowflake.

### 3. ML Forecasting

A LightGBM model predicts units to produce per store, per item, per 15-minute slot, trained on features recomputed in-memory from Neon (`slot_index`, `sale_hour`, `sale_minute`, `day_of_week`, `is_weekend`, `avg_slot_quantity`, `sample_size`, `temp_f`, `precip`, and encoded `store_id`/`item_id`).

Inference covers all 672 slots × 12 stores × 45 active items, minus rows outside each item's `time_of_day` availability window. Items with fewer than 4 historical data points fall back to category-level averages from `public.cold_start_profile`. The same inference function (`generate_production_plan()`) backs both the dashboard's static weekly grid (neutral weather placeholder — that grid has no calendar date) and the A/B comparison's daily runs (real per-date weather, a "perfect forecast" simplification since the weather itself is synthetic).

### 4. Streamlit Dashboard

**Live at [kitchensync.streamlit.app](https://kitchensync.streamlit.app).**

Predictions, stockout, and waste figures are all read live from Neon — no stale ETL window. "Now" is anchored to Neon's own clock (`MAX(created_at)` from `sales_events`), not wall-clock time, since the EC2 simulator's sim clock can drift from real time. The dashboard displays two production queues matching the real KPS layout:

- **Kitchen** — sandwiches, sides, roller grill items
- **Chicken** — chicken pieces and appetizers

Each table shows predicted units and missed demand (units lost to stockouts). Kitchen staff can check off completed batches — done items move to a completed table and are removed from the active queue, with session state persisting checkboxes across the 5-minute auto-refresh. A waste summary below shows units sold, total sales revenue, and waste percentage per category group, also computed live from Neon.

### 5. A/B Comparison

`scripts/run_daily_simulation.py` runs two parallel in-memory simulations against identical seeded Poisson demand — no API calls, no database writes:

- **ML system** — reads `public.predictions` (LightGBM, 15-min grain, real per-date weather); production fires every slot boundary (96 checks/day)
- **Baseline system** — reads `public.baseline_profile` (hourly grain, no weather axis — structurally can't have one); production fires at hour boundaries (24 checks/day)

Results are appended to `data/ab_results_v2.json`. The nightly cron job runs this after rebuilding the baseline profile, then commits and pushes the JSON to GitHub for the Astro portfolio site to pick up.

`scripts/weather_impact_analysis.py` runs a larger, reproducible version of the same comparison on demand: it buckets many simulated store-days by that day's region weather and compares ML vs. baseline within each bucket, writing `data/weather_impact_results.json`.

> **Honest finding:** on extreme-temperature days, ML beats the baseline by **+2.0pp service level** (extreme heat: 97.4% vs. 95.4%; extreme cold: 97.1% vs. 95.1%), roughly **3x** the +0.7pp gap on neutral-weather days — the model is clearly exploiting the weather signal the baseline structurally can't use. But on precipitation days, ML's service level is *marginally below* the baseline's (96.4% vs. 97.0%, a **-0.58pp** gap): the production logic's `ceil()`-driven rounding tax bites harder when ML's correctly-low precip-day predictions sit near the round-up threshold, while the baseline's flat, weather-blind average avoids the trap by accident. ML still wins decisively on waste in that same bucket (9.8% vs. 18.3%) — this is reported as a real, mixed result rather than tuned away.

---

## Key Design Decisions

**Per-store Postgres schemas**
Each store gets its own schema in Neon, so `search_path` scopes all queries automatically. Simpler connection management and a realistic multi-tenant pattern — intentionally doesn't scale past ~50 stores, where per-schema DDL migrations get painful.

**15-minute slot grain for ML**
Rather than predicting hourly demand, the model operates at 15-minute resolution — 96 slots per day, 672 per week — matching the real KPS planning cycle and letting the simulator consume predictions directly with no aggregation step.

**No minimum-batch floor**
An earlier version scaled a minimum cook quantity by hourly traffic to avoid under-production during rush. Removed deliberately: a floor forces low-traffic stores to overproduce relative to their genuinely thin demand, which is worse than the alternative. The current formula only rounds up, never pads.

**Synthetic weather as a controlled, ground-truth-only signal**
`simulator/weather.py` generates a deterministic `(temp_f, precip)` axis per store-region-day and uses it to *generate* demand data — but the ML model only ever sees the raw values as features and has to learn the demand relationship itself; it's never handed the multiplier directly. This makes the weather-driven A/B gap a genuine test of whether the model learned something the baseline structurally cannot access, not a rigged comparison.

**Retraining is manual**
The nightly cron only rebuilds the baseline profile and runs the A/B comparison — it never retrains. The model is retrained via a short manual playbook (see `CLAUDE.md`) and the resulting `.joblib` files are committed to git, since the production EC2 instance is too small to train the model itself.

**Baseline never writes to Neon**
The A/B baseline is purely in-memory. Only the ML system generates training data — letting baseline behavior write to Neon would corrupt the model's own learning signal over time.

**LightGBM over Prophet**
Prophet is a black box for interviews. LightGBM allows explicit feature engineering that can be explained and defended — time-of-day profiles, cold-start fallbacks, the weather axis, label encoding choices — all of which are meaningful talking points.

**Snowflake retired, not just suspended**
The project originally ran Neon (transactional) alongside Snowflake + dbt (analytics/training). Snowflake compute cost kept climbing even while suspended by default, so every remaining Snowflake-touching code path — extract, dbt-against-Snowflake, export-back-to-Neon — was deleted and replaced with Neon-native Python ports of the same logic. The dbt project itself wasn't deleted; it stays in the repo as a portfolio artifact showing the transformation-layer approach, just disconnected from anything live.

**Ingest API retired in favor of batched direct writes**
An earlier version had the simulator POST every sale/waste/stockout event to a FastAPI ingest service, which wrote to Neon through a connection pool held open for the service's entire lifetime. That idle-but-open connection is enough on its own to block Neon's autosuspend — Neon only suspends compute once there are zero active connections — so running the simulator and its ingest API continuously exhausted the free tier's monthly compute-hour allowance in about a week, independent of how much traffic was actually flowing. The fix removed the ingest API entirely (nothing else called it — the dashboard already reads Neon directly) and had the simulator buffer events in memory, flushing each store in one bulk insert every 5 minutes over a connection opened and closed just for that flush, matching the batch-insert pattern the historical generators already used for backfills.

---

## Project Structure

```
kitchensync/
├── config/
│   ├── menu.yaml               # Items: id, category, hold_time, cook_time, popularity, active
│   └── stores.yaml             # 12 stores, 4 regions, traffic levels 1–4
├── data/
│   ├── ab_results.json         # Frozen pre-retune archive
│   ├── ab_results_v2.json      # Live nightly A/B output (read by portfolio site)
│   └── weather_impact_results.json # Bucketed ML-vs-baseline weather comparison, manual/on-demand
├── simulator/
│   ├── pos_simulator.py        # Live async simulator — buffers events, flushes to Neon every 5 min
│   ├── historical_generator.py       # Historical data generator (one execute_values call per day)
│   ├── fast_historical_generator.py  # Same generator, one call per store — prefer for bulk reseeding
│   └── weather.py              # Deterministic synthetic weather, ground-truth-only
├── api/
│   └── db/connection.py        # Neon connection pool (dashboard + one-off scripts only), per-store search_path
├── dbt/                        # Portfolio-only — staging → intermediate → marts (not run live)
├── ml/
│   ├── features.py             # FEATURE_COLS; recomputes training features from Neon in-memory
│   ├── train.py                # LightGBM training
│   └── predict.py              # generate_production_plan() — shared inference entry point
├── dashboard/
│   ├── app.py                  # Streamlit entry point
│   ├── components/             # production_plan.py, store_selector.py
│   └── utils/data_fetch.py     # All reads live from Neon
├── scripts/
│   ├── init_db.py                    # One-time Neon schema creation
│   ├── build_baseline_profile.py     # Neon-native nightly feature rebuild
│   ├── build_cold_start_profile.py
│   ├── build_traffic_ratio.py
│   ├── build_training_features.py    # In-memory only — not persisted to Neon (storage cap)
│   ├── generate_weather_seed.py
│   ├── run_pipeline.py               # Nightly cron: build_baseline_profile → A/B → git push
│   ├── run_daily_simulation.py       # A/B comparison — ML vs baseline, outputs ab_results_v2.json
│   ├── weather_impact_analysis.py    # Bucketed weather comparison, manual/on-demand
│   └── delete_simulation_data.py     # Wipes simulation data from Neon
├── Dockerfile                  # Shared simulator/dashboard image (production uses EC2 + systemd)
└── docker-compose.yml          # Full stack: simulator + dashboard
```

---

## Setup

### Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) — `pip install uv`
- Neon account (free tier sufficient)

### Environment Variables

```bash
cp .env.example .env
```

Fill in Neon, API, and simulator credentials. See `.env.example` for all required fields.

### Install Dependencies

```bash
uv sync
```

### First-Time Setup

```bash
# 1. Initialize Neon schemas (one time only)
PYTHONPATH=. uv run python scripts/init_db.py

# 2. Generate historical seed data (window set by START_DATE in the generator)
PYTHONPATH=. uv run python -m simulator.fast_historical_generator

# 3. Build the nightly feature tables once, manually, so training has data
PYTHONPATH=. uv run python scripts/build_baseline_profile.py
PYTHONPATH=. uv run python scripts/build_cold_start_profile.py
PYTHONPATH=. uv run python scripts/build_traffic_ratio.py

# 4. Train and predict
PYTHONPATH=. uv run python -m ml.train
PYTHONPATH=. uv run python -m ml.predict
```

### Running the System

```bash
# Terminal 1 — Streamlit dashboard
PYTHONPATH=. uv run streamlit run dashboard/app.py

# Terminal 2 — Live POS simulator
PYTHONPATH=. uv run python -m simulator.pos_simulator
```

### Running the A/B Comparison

```bash
PYTHONPATH=. uv run python scripts/run_daily_simulation.py
```

Results are written to `data/ab_results_v2.json`. Run this after retraining (`python -m ml.train` then `python -m ml.predict`) for fresh predictions.

---

## AWS Deployment

The live system runs on AWS EC2:

- **API** and **simulator** run as systemd services (auto-restart on crash or reboot)
- **Nightly cron (2am UTC)**, single crontab entry on EC2:
  ```
  0 2 * * * cd /home/ubuntu/kitchensync && git pull --rebase origin master && PYTHONPATH=. /home/ubuntu/.local/bin/uv run python scripts/run_pipeline.py >> logs/pipeline.log 2>&1
  ```
  runs `build_baseline_profile.py` → A/B comparison → `git push` (retraining is a separate manual playbook — see `CLAUDE.md`)

Systemd service files are in `deploy/` (not committed — contain credentials).

---

## Store & Menu Configuration

**12 stores** across 4 Midwest regions (West Wisconsin, South Wisconsin, Minnesota, Iowa). Traffic levels 1–4 control simulated sales volume.

**45 active menu items** across 5 categories: `sandwich`, `side`, `roller_grill`, `chicken`, `appetizer`. Items map to two dashboard production queues:
- **Kitchen** — sandwich + side + roller_grill
- **Chicken** — chicken + appetizer

New items added to `config/menu.yaml` are automatically handled by the cold-start fallback until sufficient sales history accumulates (threshold: 4 data points). Set `active: false` to retire an item without touching any code.

---

## Simulated Timeline

| Period | Data |
|---|---|
| ~70-day window ending at simulator startup | Synthetic historical data, generated via `simulator/fast_historical_generator.py`, weather-aware; window set by `START_DATE` at the top of the file |
| From simulator startup onward | Live simulation, resuming from Neon's last recorded event timestamp on restart |
