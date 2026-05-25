# Per-store production plan table

import streamlit as st # type:ignore

def highlight_cells(row):
    """
    Style rows based on urgency and missed demand.
    """
    styles = [''] * len(row)

    # 1. Highlight the entire row if it's URGENT
    if row['urgency_flag'] == 'URGENT':
        styles = ['background-color: #ff4b4b; color: white'] * len(row)

    # 2. Specifically highlight the 'missed_units' cell if there are stockouts
    # We find the index of 'missed_units' in the columns
    col_idx = row.index.get_loc('missed_units')
    if row['missed_units'] > 0:
        styles[col_idx] = 'background-color: #ffa500; color: black; font-weight: bold'

    return styles

def production_plan(df):
    st.subheader("Current Production Queue")
    
    # 1. Initialize session state for the 'Done' list if it doesn't exist
    if "done_items" not in st.session_state:
        st.session_state.done_items = set()

    # 2. Pre-populate the 'done' column based on our persistent memory
    # We use item_id as the key
    df["done"] = df["item_id"].apply(lambda x: x in st.session_state.done_items)
        
    # Apply our custom styling
    styled_df = df.style.apply(highlight_cells, axis=1)
    
    # 3. Display as an interactive data editor
    edited_df = st.data_editor(
        styled_df,
        column_config={
            "done": st.column_config.CheckboxColumn(
                "Complete",
                help="Mark this batch as placed on the warming rack",
                default=False,
            ),
            "item_id": "Item",
            "predicted_units": "Planned",
            "urgency_flag": "Status",
            "missed_units": st.column_config.NumberColumn(
                "Missed Demand",
                help="Units requested by customers while out of stock"
            )
        },
        disabled=["item_id", "predicted_units", "urgency_flag", "missed_units"],
        hide_index=True,
        use_container_width=True,
        key="prod_editor" # Static key prevents unnecessary re-renders
    )
    
    # 4. UPDATE MEMORY: Check which items were marked as done in this session
    # We look at the 'done' column of the edited dataframe
    current_done = set(edited_df[edited_df["done"] == True]["item_id"])
    
    # Update our persistent state
    st.session_state.done_items.update(current_done)
    
    # Feedback for the user
    if current_done:
        st.success(f"Production acknowledged for {len(current_done)} items.")