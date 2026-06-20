from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List


class StoreBase(BaseModel):
    store_code: str
    store_name: str
    address: Optional[str] = None
    contact_phone: Optional[str] = None
    manager_name: Optional[str] = None


class StoreCreate(StoreBase):
    pass


class StoreUpdate(BaseModel):
    store_name: Optional[str] = None
    address: Optional[str] = None
    contact_phone: Optional[str] = None
    manager_name: Optional[str] = None


class StoreResponse(StoreBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime
