from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship

from ..database import Base


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    store_code = Column(String(20), unique=True, index=True, nullable=False)
    store_name = Column(String(100), nullable=False)
    address = Column(String(200))
    contact_phone = Column(String(20))
    manager_name = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("User", back_populates="store")
    patients = relationship("Patient", back_populates="store")
    tasks = relationship("CallbackTask", back_populates="store")
