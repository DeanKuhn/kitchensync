# Pydantic models for events

from pydantic import BaseModel

class SalesEvent(BaseModel):
    item_id: str
    quantity: int
    price: float
    hold_time: int

class WasteEvent(BaseModel):
    item_id: str
    quantity: int
    reason: str

class InventoryEvent(BaseModel):
    item_id: str
    quantity: int