select
    store_id,
    item_id,
    count(*) as denominator,
    count_if(urgency_flag = 'URGENT') as numerator,
    (count_if(urgency_flag = 'URGENT')) /
        (nullif(count(*), 0)::float) as urgency_rate

from {{ source('marts', 'predictions') }}
where predicted_at >= dateadd(hour, -24, current_timestamp())
group by store_id, item_id