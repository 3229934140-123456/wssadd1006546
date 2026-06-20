from pydantic import BaseModel, ConfigDict
from datetime import datetime, time
from typing import Optional, List
from ..models.rule import CallTimeWindow


class CallbackRuleBase(BaseModel):
    rule_name: str
    treatment_type_id: int
    days_after_treatment: int
    call_time_window: CallTimeWindow = CallTimeWindow.EVENING
    custom_call_time: Optional[time] = None
    script_template: str
    abnormal_keywords: Optional[str] = None
    is_active: bool = True
    priority: int = 0


class CallbackRuleCreate(CallbackRuleBase):
    pass


class CallbackRuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    treatment_type_id: Optional[int] = None
    days_after_treatment: Optional[int] = None
    call_time_window: Optional[CallTimeWindow] = None
    custom_call_time: Optional[time] = None
    script_template: Optional[str] = None
    abnormal_keywords: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None


class CallbackRuleResponse(CallbackRuleBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    treatment_type: Optional["TreatmentTypeResponse"] = None
    created_at: datetime
    updated_at: datetime


from .treatment import TreatmentTypeResponse
CallbackRuleResponse.model_rebuild()
