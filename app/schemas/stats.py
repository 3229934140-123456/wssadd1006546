from pydantic import BaseModel
from datetime import date, datetime
from typing import Optional, List
from enum import Enum


class StatGroupBy(str, Enum):
    STORE = "store"
    USER = "user"
    DATE = "date"


class StatsRequest(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    store_id: Optional[int] = None


class StoreStats(BaseModel):
    store_id: int
    store_name: str
    total_tasks: int = 0
    completed_tasks: int = 0
    completion_rate: float = 0.0
    abnormal_tasks: int = 0
    abnormal_rate: float = 0.0
    timeout_tasks: int = 0
    doctor_review_tasks: int = 0
    review_closed: int = 0
    review_closure_rate: float = 0.0


class UserStats(BaseModel):
    user_id: int
    user_name: str
    role: str
    total_tasks: int = 0
    completed_tasks: int = 0
    completion_rate: float = 0.0
    abnormal_tasks: int = 0
    avg_call_duration: float = 0.0


class TimeoutTaskItem(BaseModel):
    task_id: int
    task_no: str
    patient_name: str
    phone: str
    store_name: str
    scheduled_date: date
    due_time: Optional[datetime] = None
    status: str
    overdue_hours: float
    treatment_type: Optional[str] = None
    assigned_user: Optional[str] = None


class AbnormalTaskItem(BaseModel):
    task_id: int
    task_no: str
    patient_name: str
    phone: str
    store_name: str
    scheduled_date: date
    status: str
    abnormal_keywords_hit: Optional[str] = None
    treatment_type: Optional[str] = None
    assigned_user: Optional[str] = None
    doctor_review_notes: Optional[str] = None
    doctor_conclusion: Optional[str] = None
    review_status: Optional[str] = None


class RuleEffectItem(BaseModel):
    treatment_type_id: int
    treatment_type_name: str
    rule_id: int
    rule_name: str
    call_time_window: Optional[str] = None
    total_tasks: int = 0
    abnormal_tasks: int = 0
    abnormal_rate: float = 0.0
    timeout_tasks: int = 0
    timeout_rate: float = 0.0
    doctor_review_tasks: int = 0
    doctor_review_rate: float = 0.0


class StatsOverview(BaseModel):
    total_tasks: int = 0
    pending_tasks: int = 0
    in_progress_tasks: int = 0
    completed_tasks: int = 0
    completion_rate: float = 0.0
    abnormal_tasks: int = 0
    abnormal_rate: float = 0.0
    timeout_tasks: int = 0
    doctor_review_tasks: int = 0
    doctor_reviewed_tasks: int = 0
    review_pending_doctor: int = 0
    review_doctor_advised: int = 0
    review_pending_followup: int = 0
    review_closed: int = 0
    review_closure_rate: float = 0.0
    review_doctor_overdue: int = 0
    review_followup_overdue: int = 0


class StatsFilterOptions(BaseModel):
    stores: List[dict] = []
    users: List[dict] = []
    treatment_types: List[dict] = []
    rules: List[dict] = []
