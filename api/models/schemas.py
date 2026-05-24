# Pydantic models for events

from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class SalesEvent(BaseModel):
    item_id: str
    quantity: int
    price: float
    created_at: datetime

class WasteEvent(BaseModel):
    item_id: str
    quantity: int
    reason: str
    created_at: datetime

class InventoryEvent(BaseModel):
    item_id: str
    quantity: int