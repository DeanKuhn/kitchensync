with profile as (

    select * from {{ ref('int_sales__time_of_day_profile') }}

),

menu as (

    select * from {{ ref('menu_items') }}

),

final as (

    select
        p.day_of_week,
        p.sale_hour,
        p.slot_index,
        avg(p.avg_slot_quantity) as avg_slot_quantity,
        m.category

    from profile p
    inner join menu m on p.item_id = m.item_id

    group by
        -- important to group by category to get category average
        category,
        day_of_week,
        sale_hour,
        slot_index

)

select * from final