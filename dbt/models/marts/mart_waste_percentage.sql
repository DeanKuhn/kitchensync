with waste as (

    select * from {{ ref('stg_waste_log') }}

),


sales as (

    select * from {{ ref('stg_sales_events') }}

),


final as (
    select
        w.store_id,
        w.item_id,
        sum(w.quantity) as waste_quantity,
        sum(s.quantity) as sale_quantity,
        w.waste_date as date,
        (sum(w.quantity) / sum(s.quantity)::float) * 100 as waste_percentage

    from waste w
    inner join sales s
    on w.store_id = s.store_id
    and w.item_id = s.item_id
    and w.waste_date = s.sale_date

    group by
        w.store_id,
        w.item_id,
        w.waste_date

)


select * from final