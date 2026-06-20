from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Text, Date, Time
from sqlalchemy.orm import relationship
import enum

from ..database import Base


class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABNORMAL = "abnormal"
    DOCTOR_REVIEW = "doctor_review"
    DOCTOR_REVIEWED = "doctor_reviewed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class CallResult(str, enum.Enum):
    CONNECTED = "connected"
    NO_ANSWER = "no_answer"
    REJECTED = "rejected"
    POWER_OFF = "power_off"
    WRONG_NUMBER = "wrong_number"
    OTHER = "other"


class CallbackTask(Base):
    __tablename__ = "callback_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_no = Column(String(30), unique=True, index=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    treatment_record_id = Column(Integer, ForeignKey("treatment_records.id"), nullable=False)
    rule_id = Column(Integer, ForeignKey("callback_rules.id"), nullable=False)

    scheduled_date = Column(Date, nullable=False)
    scheduled_time = Column(Time, nullable=True)
    due_time = Column(DateTime, nullable=True)

    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    priority = Column(Integer, default=0)

    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime, nullable=True)

    handled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    handled_at = Column(DateTime, nullable=True)

    call_result = Column(Enum(CallResult), nullable=True)
    call_duration_seconds = Column(Integer, default=0)
    callback_notes = Column(Text)
    abnormal_keywords_hit = Column(String(500))
    is_abnormal = Column(Boolean, default=False)

    reassigned_from_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reassigned_at = Column(DateTime, nullable=True)
    reassigned_reason = Column(String(200))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient", back_populates="tasks")
    store = relationship("Store", back_populates="tasks")
    treatment_record = relationship("TreatmentRecord", back_populates="tasks")
    rule = relationship("CallbackRule", back_populates="tasks")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id], back_populates="assigned_tasks")
    handled_by = relationship("User", foreign_keys=[handled_by_id], back_populates="handled_tasks")
