from pydantic import BaseModel
from datetime import date
from typing import Optional
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
    status: str
    overdue_hours: float


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
