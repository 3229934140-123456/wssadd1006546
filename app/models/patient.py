from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
import enum

from ..database import Base


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    patient_no = Column(String(30), unique=True, index=True, nullable=False)
    name = Column(String(50), nullable=False)
    gender = Column(Enum(Gender), nullable=False)
    age = Column(Integer, nullable=False)
    phone = Column(String(20), nullable=False)
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.LOW)
    risk_tags = Column(String(500))
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    store = relationship("Store", back_populates="patients")
    treatments = relationship("TreatmentRecord", back_populates="patient", cascade="all, delete-orphan")
    tasks = relationship("CallbackTask", back_populates="patient")
