with current_sales as (

    select
        r.store_id,
        r.item_id,
        r.sale_date,
        r.sale_hour,
        r.day_of_week,
        r.rolling_2hr

    from {{ ref('int_sales__rolling_features') }} r

    qualify row_number() over (
        partition by r.store_id, r.item_id
        order by r.sale_date desc, r.sale_hour desc
    ) = 1

),


profile as (

    select * from {{ ref('int_sales__time_of_day_profile') }}

),


final as (

    select
        cs.store_id,
        cs.item_id,
        cs.sale_date,
        cs.sale_hour,
        cs.rolling_2hr as current_units,
        p.avg_hourly_quantity as baseline_units,
        cs.rolling_2hr / nullif(p.avg_hourly_quantity, 0) as velocity_ratio,
        case
            when (cs.rolling_2hr / nullif(p.avg_hourly_quantity, 0)) >=
                {{ var('urgency_threshold') }}
            then 'URGENT' else 'NORMAL'
        end as urgency_flag

        from current_sales cs
        left join profile p
            on cs.store_id      = p.store_id
            and cs.item_id      = p.item_id
            and cs.day_of_week  = p.day_of_week
            and cs.sale_hour    = p.sale_hour

)


select * from final


/*

--- DATA TRANSFORMATION VISUALIZATION ---

STEP 1: current_sales (Using QUALIFY to get ONLY the latest snapshot)
STORE_ID | ITEM_ID | SALE_DATE  | SALE_HOUR | CURRENT_UNITS (2HR)
store_01 | BURGER  | 2026-02-12 | 14        | 18

STEP 2: final (Calculating Real-Time Velocity vs Baseline)
ITEM_ID | CURRENT | BASELINE | VELOCITY_RATIO | URGENCY_FLAG
BURGER  | 18      | 9.0      | 2.0            | URGENT (Ratio >= Threshold)

*/