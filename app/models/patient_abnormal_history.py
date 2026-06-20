from datetime import datetime, date
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Date
from sqlalchemy.orm import relationship

from ..database import Base


class PatientAbnormalHistory(Base):
    __tablename__ = "patient_abnormal_history"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("callback_tasks.id"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)

    abnormal_keywords_hit = Column(String(500))
    callback_notes = Column(Text)
    doctor_review_notes = Column(Text)
    doctor_conclusion = Column(String(50))
    suggested_review_date = Column(Date)
    nurse_followup_notes = Column(Text)
    followup_result = Column(String(100))
    actual_review_date = Column(Date)
    closure_reason = Column(String(200))

    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, default=datetime.utcnow)

    patient = relationship("Patient")
    task = relationship("CallbackTask")
    store = relationship("Store")
