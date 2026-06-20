from datetime import datetime, time
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Enum, Text, Time
from sqlalchemy.orm import relationship
import enum

from ..database import Base


class CallTimeWindow(str, enum.Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    CUSTOM = "custom"


class CallbackRule(Base):
    __tablename__ = "callback_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_name = Column(String(100), nullable=False)
    treatment_type_id = Column(Integer, ForeignKey("treatment_types.id"), nullable=False)
    days_after_treatment = Column(Integer, nullable=False, comment="治疗后第几天回访，0表示当天")
    call_time_window = Column(Enum(CallTimeWindow), default=CallTimeWindow.EVENING)
    custom_call_time = Column(Time, nullable=True)
    script_template = Column(Text, nullable=False, comment="标准问询话术模板")
    abnormal_keywords = Column(String(500), comment="异常关键词列表，逗号分隔，命中需转医生")
    is_active = Column(Boolean, default=True)
    priority = Column(Integer, default=0, comment="优先级，数字越大优先级越高")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    treatment_type = relationship("TreatmentType", back_populates="callback_rules")
    tasks = relationship("CallbackTask", back_populates="rule")
