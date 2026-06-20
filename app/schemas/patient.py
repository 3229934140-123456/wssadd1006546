from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List
from ..models.patient import RiskLevel, Gender


class PatientBase(BaseModel):
    patient_no: str
    name: str
    gender: Gender
    age: int
    phone: str
    risk_level: RiskLevel = RiskLevel.LOW
    risk_tags: Optional[str] = None
    store_id: int


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    name: Optional[str] = None
    gender: Optional[Gender] = None
    age: Optional[int] = None
    phone: Optional[str] = None
    risk_level: Optional[RiskLevel] = None
    risk_tags: Optional[str] = None
    store_id: Optional[int] = None


class PatientResponse(PatientBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class PatientDetailResponse(PatientResponse):
    pass
