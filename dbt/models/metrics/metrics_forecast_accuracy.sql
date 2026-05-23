-- Compares predicted units from MARTS.PREDICTIONS table against
-- actual units from mart_store_sales.
-- Computes MAE and RMSE per store + item.
-- Depends on: MARTS.PREDICTIONS, int_sales__rolling_features


with predictions_enriched as (

    select
        r.store_id,
        r.item_id,
        r.predicted_units,
        date(dateadd(hour, 1, predicted_at)) as outcome_date,
        hour(dateadd(hour, 1, predicted_at)) as outcome_hour,
        f.hourly_quantity

    from {{ source('marts', 'predictions') }} r

    inner join {{ ref('int_sales__rolling_features') }} f
    on r.store_id = f.store_id
    and r.item_id = f.item_id
    and date(dateadd(hour, 1, r.predicted_at)) = f.sale_date
    and hour(dateadd(hour, 1, r.predicted_at)) = f.sale_hour

),


metric_forecast_accuracy as (
    select
        store_id,
        item_id,
        avg(abs(predicted_units - hourly_quantity)) as mae,
        sqrt(avg(power((predicted_units - hourly_quantity), 2))) as RMSE

    from predictions_enriched
    group by store_id, item_id

)


select * from metric_forecast_accuracy