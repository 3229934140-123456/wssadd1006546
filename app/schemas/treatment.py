from pydantic import BaseModel, ConfigDict
from datetime import datetime, date
from typing import Optional


class TreatmentTypeBase(BaseModel):
    type_code: str
    type_name: str
    description: Optional[str] = None


class TreatmentTypeCreate(TreatmentTypeBase):
    pass


class TreatmentTypeUpdate(BaseModel):
    type_name: Optional[str] = None
    description: Optional[str] = None


class TreatmentTypeResponse(TreatmentTypeBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class TreatmentRecordBase(BaseModel):
    patient_id: int
    treatment_type_id: int
    treatment_date: date
    doctor_name: Optional[str] = None
    tooth_position: Optional[str] = None
    treatment_notes: Optional[str] = None


class TreatmentRecordCreate(TreatmentRecordBase):
    pass


class TreatmentRecordUpdate(BaseModel):
    treatment_type_id: Optional[int] = None
    treatment_date: Optional[date] = None
    doctor_name: Optional[str] = None
    tooth_position: Optional[str] = None
    treatment_notes: Optional[str] = None


class TreatmentRecordResponse(TreatmentRecordBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    treatment_type: Optional[TreatmentTypeResponse] = None
    patient: Optional["PatientResponse"] = None
    created_at: datetime
    updated_at: datetime


from .patient import PatientResponse
TreatmentRecordResponse.model_rebuild()
