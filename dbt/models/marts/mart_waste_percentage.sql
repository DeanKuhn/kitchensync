with waste as (

    select
        store_id,
        item_id,
        waste_date,
        sum(quantity) as waste_quantity

    from {{ ref('stg_waste_log') }}

    group by
        store_id,
        item_id,
        waste_date

),


sales as (

    select
        store_id,
        item_id,
        sale_date,
        sum(quantity) as sale_quantity

    from {{ ref('stg_sales_events') }}

    group by
        store_id,
        item_id,
        sale_date

),


menu as (

    select
        item_id,
        area,
        category,
        price,
        cost

    from {{ ref('menu_items') }}

),


final as (
    select
        w.store_id,
        w.item_id,
        m.area,
        m.category,
        (w.waste_quantity * m.cost) as waste_cost,
        (s.sale_quantity * m.price) as sale_revenue,
        w.waste_date,
        ((w.waste_quantity * m.cost) / nullif(s.sale_quantity * m.price, 0)) * 100
            as waste_percentage

    from waste w
    inner join sales s
    on w.store_id = s.store_id
    and w.item_id = s.item_id
    and w.waste_date = s.sale_date
    inner join menu m
    on w.item_id = m.item_id

)


select * from final