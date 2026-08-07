# dbt project — portfolio-only

This dbt project is kept in the repo as a demonstration of a modern
transformation stack (staging → intermediate → marts, tests, macros), but it
is **not part of the live pipeline**. As of 2026-08, Snowflake was retired
entirely (cost-driven — see CLAUDE.md decision #20) and every model this
project defines has a Neon-native Python equivalent that runs instead:

| dbt model | Neon-native replacement |
|---|---|
| `int_sales__time_of_day_profile` | `scripts/build_baseline_profile.py` |
| `mart_cold_start_profile` | `scripts/build_cold_start_profile.py` |
| `mart_store_traffic_ratio` | `scripts/build_traffic_ratio.py` |
| `mart_ml_training_features` | `scripts/build_training_features.py` (called in-memory by `ml/features.py`) |

`ml/predict.py` reads/writes Neon directly and never touches Snowflake or
these dbt models.

If you want to run this project anyway (e.g. to see the SQL/testing
approach), it still works standalone against a Snowflake account — see the
`SNOWFLAKE_*` variables in `.env.example` and the dbt commands in CLAUDE.md.
Nothing in the live app depends on you doing so.
