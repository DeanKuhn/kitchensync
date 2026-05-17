# POST endpoints defined

# Import FastAPI router and special HTTPException
from fastapi import APIRouter, HTTPException # type:ignore

# Import Pydantic schemas for schema verification
from api.models.schemas import SalesEvent, WasteEvent, InventoryEvent

# Import db connection with special search_path function
from api.db.connection import get_store_connection, release_connection

router = APIRouter()


# Updated to release pool connection instad of just connection.close()
def close_and_commit(connection, cursor):
    connection.commit()
    cursor.close()
    release_connection(connection)


def close_not_commit(connection, cursor):
    cursor.close()
    release_connection(connection)



@router.post("/{store_id}/sales")
def create_sales_event(store_id: str, event: SalesEvent):

    # Establish connection with database using the function that gives a
    # search_path based on store id so there is not need to distinguish schema
    connection = get_store_connection(store_id)
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO sales_events (item_id, quantity, price)
            VALUES (%s, %s, %s);
        """, (event.item_id, event.quantity, event.price))

        close_and_commit(connection, cursor)

        # Return something showing that the insertion went through smoothly
        return {"status": "ok", "store_id": store_id}

    except Exception as e:
        close_not_commit(connection, cursor)

        # Special error raised by FastAPI; returns 500 code meaning something
        # went wrong
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{store_id}/waste")
def create_waste_event(store_id: str, event: WasteEvent):

    connection = get_store_connection(store_id)
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT into waste_log (item_id, quantity, reason)
            VALUES (%s, %s, %s);
        """, (event.item_id, event.quantity, event.reason))

        close_and_commit(connection, cursor)
        return {"status": "ok", "store_id": store_id}

    except Exception as e:
        close_not_commit(connection, cursor)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{store_id}/inventory")
def create_inventory_event(store_id: str, event: InventoryEvent):

    connection = get_store_connection(store_id)
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT into inventory_snapshots (item_id, quantity)
            VALUES (%s, %s);
        """, (event.item_id, event.quantity))

        close_and_commit(connection, cursor)
        return {"status": "ok", "store_id": store_id}

    except Exception as e:
        close_not_commit(connection, cursor)
        raise HTTPException(status_code=500, detail=str(e))