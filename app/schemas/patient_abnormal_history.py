from pydantic import BaseModel, ConfigDict
from datetime import datetime, date
from typing import Optional


class PatientAbnormalHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_id: int
    abnormal_keywords_hit: Optional[str] = None
    callback_notes: Optional[str] = None
    doctor_review_notes: Optional[str] = None
    doctor_conclusion: Optional[str] = None
    suggested_review_date: Optional[date] = None
    nurse_followup_notes: Optional[str] = None
    followup_result: Optional[str] = None
    actual_review_date: Optional[date] = None
    closure_reason: Optional[str] = None
    created_at: datetime
    closed_at: datetime
