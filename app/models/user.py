from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Text, Date, Time
from sqlalchemy.orm import relationship
import enum

from ..database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    CALL_AGENT = "call_agent"
    STORE_NURSE = "store_nurse"
    DOCTOR = "doctor"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    real_name = Column(String(50), nullable=False)
    email = Column(String(100))
    hashed_password = Column(String(200), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.CALL_AGENT)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    store = relationship("Store", back_populates="users")
    assigned_tasks = relationship("CallbackTask", back_populates="assigned_user", foreign_keys="CallbackTask.assigned_user_id")
    handled_tasks = relationship("CallbackTask", back_populates="handled_by", foreign_keys="CallbackTask.handled_by_id")
