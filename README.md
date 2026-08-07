# KitchenSync

A portfolio-grade simulation of a Kwik Trip-style Kitchen Production System (KPS): a LightGBM model forecasts per-store, per-item food production at 15-minute slot grain from simulated POS data, and a Streamlit dashboard turns those forecasts into Kitchen/Chicken production queues, refreshed every 5 minutes. 12 stores, 4 regions, 45 active menu items.

A nightly A/B pipeline on AWS EC2 pits the ML system against a naive hourly-average baseline — with a synthetic weather feature giving the ML side a structural edge the baseline's date-blind lookup can't have — and pushes results to a static Astro portfolio site every morning.

**Live:** [kitchensync.streamlit.app](https://kitchensync.streamlit.app)

---

## What This Demonstrates

- **End-to-end data engineering** — async POS event ingestion → Postgres (Neon) → nightly feature rebuild → ML → live dashboard, on a cost-conscious footprint
- **Feature engineering with a controlled natural experiment** — a synthetic `(temp_f, precip)` weather axis is fed to the ML model but is structurally invisible to the baseline's lookup, isolating exactly how much a model can exploit a signal a simpler system can't use
- **Realistic simulator design** — Poisson arrivals, FIFO batch inventory, slot-boundary production logic, startup inventory seeding
- **Honest A/B evaluation, including where ML loses** — see Results below: one bucket where the baseline actually wins
- **A migrated, right-sized architecture** — originally Neon + Snowflake + dbt; Snowflake was retired entirely once cost stopped justifying it, dbt kept as a portfolio-only artifact rather than deleted

---

## Results

Bucketing simulated store-days by that day's weather (`scripts/weather_impact_analysis.py`) gives a cleaner read than the single-day nightly A/B:

| Bucket | Store-days | ML service level | Baseline | Gap | ML waste | Baseline waste |
|---|---|---|---|---|---|---|
| Extreme heat | 153 | 97.4% | 95.4% | **+2.0pp** | 7.5% | 9.1% |
| Extreme cold | 225 | 97.1% | 95.1% | **+2.0pp** | 8.4% | 9.5% |
| Neutral | 84 | 97.1% | 96.4% | +0.7pp | 7.7% | 5.9% |
| Precipitation | 258 | 96.4% | 97.0% | **-0.6pp** | 9.8% | 18.3% |

On extreme-temperature days, ML beats the baseline by roughly 3x the neutral-day gap — clear evidence it's exploiting the weather signal the baseline structurally can't access. On precipitation days, ML's service level is *marginally below* the baseline's: production logic's `ceil()`-driven rounding tax bites harder when ML's correctly-low precip predictions sit near the round-up threshold, while the baseline's flat, weather-blind average avoids the trap by accident. ML still wins decisively on waste in that same bucket. Reported as a real, mixed result rather than tuned away.

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

- **POS Simulation** — async simulator generates Poisson-distributed sales/waste/stockout events per store, shaped by an hourly rush curve and synthetic weather; buffers in memory and flushes to Neon every 5 minutes via a short-lived bulk-insert connection (no ingest API). Resumes its sim clock from Neon's last event on restart.
- **Nightly Feature Rebuild** — `scripts/build_baseline_profile.py` rebuilds `public.baseline_profile` from raw `sales_events` every night, a Neon-native port of what used to be a dbt model against Snowflake.
- **ML Forecasting** — LightGBM predicts units per store/item/15-min slot from Neon-derived features (time-of-day, weather, encoded store/item). Covers all 672 slots × 12 stores × 45 items; items with <4 data points fall back to category-level cold-start averages. `generate_production_plan()` backs both the dashboard's static grid and the A/B comparison's daily runs.
- **Streamlit Dashboard** — reads predictions, stockout, and waste live from Neon; "now" is anchored to Neon's own clock, not wall-clock. Two production queues (Kitchen: sandwich/side/roller-grill, Chicken: chicken/appetizer) with missed-demand and waste summaries, checkable batches, 5-min autorefresh.
- **A/B Comparison** — `run_daily_simulation.py` runs ML (`public.predictions`, 96 checks/day) vs. baseline (`public.baseline_profile`, 24 checks/day) against identical seeded demand, in-memory only. Nightly cron appends to `data/ab_results_v2.json` and pushes to GitHub for the portfolio site. `weather_impact_analysis.py` runs the larger bucketed version behind the Results table above.

---

## Key Design Decisions

- **Per-store Postgres schemas** — `search_path`-scoped connections, simpler than a shared multi-tenant table; intentionally doesn't scale past ~50 stores
- **15-minute slot grain** — matches the real KPS planning cycle (672 slots/week), no aggregation step between prediction and simulator
- **No minimum-batch floor** — an earlier traffic-scaled floor forced low-traffic stores to overproduce; current formula only rounds up, never pads
- **Synthetic weather is ground-truth-only** — `weather.py` generates demand data from `(temp_f, precip)`, but the model only ever sees the raw features and must learn the relationship itself — a genuine test of what the model can exploit that the baseline structurally can't
- **Retraining is manual** — nightly cron only rebuilds the baseline profile and runs the A/B comparison; the model is retrained via a short manual playbook and the `.joblib` files committed to git, since the EC2 instance is too small to train itself
- **LightGBM over Prophet** — explicit, defensible feature engineering (time-of-day profiles, cold-start fallbacks, the weather axis) over a black-box model
- **Snowflake retired, not just suspended** — compute cost kept climbing even while idle, so every Snowflake-touching path was deleted and replaced with Neon-native Python ports; dbt stays in the repo as a portfolio artifact only
- **Ingest API retired for batched direct writes** — an always-open connection pool in the old FastAPI ingest service blocked Neon's autosuspend and burned the free tier's compute-hours in about a week regardless of traffic; removed in favor of the simulator buffering events and bulk-flushing every 5 minutes over a short-lived connection

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
│   ├── fast_historical_generator.py  # Bulk seed-data generator, weather-aware
│   └── weather.py              # Deterministic synthetic weather, ground-truth-only
├── api/db/connection.py        # Neon connection pool (dashboard + one-off scripts only)
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
│   ├── build_baseline_profile.py     # Neon-native nightly feature rebuild (+ cold_start/traffic_ratio siblings)
│   ├── build_training_features.py    # In-memory only — not persisted to Neon (storage cap)
│   ├── run_pipeline.py               # Nightly cron: build_baseline_profile → A/B → git push
│   ├── run_daily_simulation.py       # A/B comparison — ML vs baseline, outputs ab_results_v2.json
│   └── weather_impact_analysis.py    # Bucketed weather comparison behind the Results table above
└── Dockerfile / docker-compose.yml   # Shared simulator/dashboard image (production uses EC2 + systemd)
```

---

## Setup

Prereqs: Python 3.12+, [uv](https://github.com/astral-sh/uv), a Neon account (free tier is enough).

```bash
cp .env.example .env    # fill in NEON_DATABASE_URL
uv sync

# One-time: schemas, historical seed data, feature tables, initial train + predict
PYTHONPATH=. uv run python scripts/init_db.py
PYTHONPATH=. uv run python -m simulator.fast_historical_generator
PYTHONPATH=. uv run python scripts/build_baseline_profile.py
PYTHONPATH=. uv run python scripts/build_cold_start_profile.py
PYTHONPATH=. uv run python scripts/build_traffic_ratio.py
PYTHONPATH=. uv run python -m ml.train
PYTHONPATH=. uv run python -m ml.predict
```

```bash
# Run it
PYTHONPATH=. uv run streamlit run dashboard/app.py          # dashboard
PYTHONPATH=. uv run python -m simulator.pos_simulator        # simulator (separate terminal)
PYTHONPATH=. uv run python scripts/run_daily_simulation.py   # A/B comparison -> data/ab_results_v2.json
```

---

## AWS Deployment

The live system runs on AWS EC2:

- **Simulator** runs as a systemd service (auto-restart on crash or reboot)
- **Nightly cron (2am UTC)**, single crontab entry on EC2:
  ```
  0 2 * * * cd /home/ubuntu/kitchensync && git pull --rebase origin master && PYTHONPATH=. /home/ubuntu/.local/bin/uv run python scripts/run_pipeline.py >> logs/pipeline.log 2>&1
  ```
  runs `build_baseline_profile.py` → A/B comparison → `git push` (retraining is a separate manual playbook — see `CLAUDE.md`)

Systemd service files are in `deploy/` (not committed — contain credentials).
