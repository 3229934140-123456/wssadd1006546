from datetime import datetime, date
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import relationship

from ..database import Base


class TreatmentType(Base):
    __tablename__ = "treatment_types"

    id = Column(Integer, primary_key=True, index=True)
    type_code = Column(String(30), unique=True, index=True, nullable=False)
    type_name = Column(String(100), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    treatment_records = relationship("TreatmentRecord", back_populates="treatment_type")
    callback_rules = relationship("CallbackRule", back_populates="treatment_type")


class TreatmentRecord(Base):
    __tablename__ = "treatment_records"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    treatment_type_id = Column(Integer, ForeignKey("treatment_types.id"), nullable=False)
    treatment_date = Column(Date, nullable=False, default=date.today)
    doctor_name = Column(String(50))
    tooth_position = Column(String(50))
    treatment_notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    patient = relationship("Patient", back_populates="treatments")
    treatment_type = relationship("TreatmentType", back_populates="treatment_records")
    tasks = relationship("CallbackTask", back_populates="treatment_record", cascade="all, delete-orphan")
