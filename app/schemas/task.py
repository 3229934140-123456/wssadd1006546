from pydantic import BaseModel, ConfigDict
from datetime import datetime, date, time
from typing import Optional, List
from enum import Enum
from ..models.task import TaskStatus, CallResult


class TaskGroup(str, Enum):
    NOW = "now"
    LATER = "later"
    OVERDUE = "overdue"


class CallbackTaskBase(BaseModel):
    pass


class GenerateTasksRequest(BaseModel):
    store_id: Optional[int] = None
    treatment_record_ids: Optional[list[int]] = None


class ReassignTaskRequest(BaseModel):
    task_id: int
    target_user_id: int
    reason: Optional[str] = None


class HandleTaskRequest(BaseModel):
    task_id: int
    call_result: CallResult
    call_duration_seconds: Optional[int] = 0
    callback_notes: Optional[str] = None
    escalate_to_doctor: Optional[bool] = False


class CompleteDoctorReviewRequest(BaseModel):
    task_id: int
    review_notes: str
    doctor_conclusion: Optional[str] = None
    suggested_review_date: Optional[date] = None


class AssignmentReasonDetail(BaseModel):
    patient_risk_level: str
    patient_risk_tags: Optional[str] = None
    has_special_tags: bool
    candidate_scores: List[dict]
    final_decision: str
    reason_summary: str


class CallbackTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    task_no: str
    patient_id: int
    store_id: int
    treatment_record_id: int
    rule_id: int
    scheduled_date: date
    scheduled_time: Optional[time] = None
    due_time: Optional[datetime] = None
    status: TaskStatus
    priority: int
    assigned_user_id: Optional[int] = None
    assigned_at: Optional[datetime] = None
    handled_by_id: Optional[int] = None
    handled_at: Optional[datetime] = None
    call_result: Optional[CallResult] = None
    call_duration_seconds: Optional[int] = None
    callback_notes: Optional[str] = None
    abnormal_keywords_hit: Optional[str] = None
    is_abnormal: bool = False
    reassigned_from_id: Optional[int] = None
    reassigned_at: Optional[datetime] = None
    reassigned_reason: Optional[str] = None
    assignment_reason: Optional[str] = None
    doctor_review_notes: Optional[str] = None
    doctor_conclusion: Optional[str] = None
    suggested_review_date: Optional[date] = None
    reviewed_by_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    patient: Optional["PatientResponse"] = None
    store: Optional["StoreResponse"] = None
    rule: Optional["CallbackRuleResponse"] = None
    treatment_record: Optional["TreatmentRecordResponse"] = None
    assigned_user: Optional["UserResponse"] = None
    reviewed_by: Optional["UserResponse"] = None


from .patient import PatientResponse
from .store import StoreResponse
from .rule import CallbackRuleResponse
from .treatment import TreatmentRecordResponse
from .user import UserResponse
CallbackTaskResponse.model_rebuild()


class TaskListResponse(BaseModel):
    items: list[CallbackTaskResponse]
    total: int
    page: int
    page_size: int


class TaskGroupStats(BaseModel):
    now_count: int = 0
    later_count: int = 0
    overdue_count: int = 0
    active_group: TaskGroup = TaskGroup.NOW


class GroupedTaskResponse(BaseModel):
    stats: TaskGroupStats
    tasks: TaskListResponse

