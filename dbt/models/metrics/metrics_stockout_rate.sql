-- Compares the urgency rate grouped by store and item
-- Takes count over 24 hours, so it is operationally useful to find brief
-- trends in time for a store


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