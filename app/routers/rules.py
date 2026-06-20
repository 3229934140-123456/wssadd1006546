from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from ..database import get_db
from ..deps import get_current_user, get_current_active_admin, require_roles
from ..models import CallbackRule, TreatmentType, User, UserRole
from ..schemas.rule import CallbackRuleCreate, CallbackRuleUpdate, CallbackRuleResponse

router = APIRouter(prefix="/api/rules", tags=["回访规则配置"])


@router.get("", response_model=List[CallbackRuleResponse])
def list_rules(
    treatment_type_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CallbackRule).options(joinedload(CallbackRule.treatment_type))
    if treatment_type_id:
        query = query.filter(CallbackRule.treatment_type_id == treatment_type_id)
    if is_active is not None:
        query = query.filter(CallbackRule.is_active == is_active)
    total = query.count()
    items = query.order_by(
        CallbackRule.priority.desc(),
        CallbackRule.treatment_type_id.asc(),
        CallbackRule.days_after_treatment.asc()
    ).offset((page - 1) * page_size).limit(page_size).all()
    return items


@router.post("", response_model=CallbackRuleResponse)
def create_rule(
    data: CallbackRuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    ttype = db.query(TreatmentType).filter(TreatmentType.id == data.treatment_type_id).first()
    if not ttype:
        raise HTTPException(status_code=400, detail="治疗类型不存在")
    existing = db.query(CallbackRule).filter(
        (CallbackRule.treatment_type_id == data.treatment_type_id) &
        (CallbackRule.days_after_treatment == data.days_after_treatment) &
        (CallbackRule.is_active == True)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="该治疗类型此天数已有激活规则，如需修改请停用旧规则或编辑")
    obj = CallbackRule(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/{rule_id}", response_model=CallbackRuleResponse)
def get_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    obj = db.query(CallbackRule).options(joinedload(CallbackRule.treatment_type)).filter(
        CallbackRule.id == rule_id
    ).first()
    if not obj:
        raise HTTPException(status_code=404, detail="规则不存在")
    return obj


@router.put("/{rule_id}", response_model=CallbackRuleResponse)
def update_rule(
    rule_id: int,
    data: CallbackRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    obj = db.query(CallbackRule).filter(CallbackRule.id == rule_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="规则不存在")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/{rule_id}")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    obj = db.query(CallbackRule).filter(CallbackRule.id == rule_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="规则不存在")
    db.delete(obj)
    db.commit()
    return {"message": "删除成功"}


@router.post("/{rule_id}/toggle")
def toggle_rule_status(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    obj = db.query(CallbackRule).filter(CallbackRule.id == rule_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="规则不存在")
    obj.is_active = not obj.is_active
    db.commit()
    db.refresh(obj)
    return {"message": f"规则已{'激活' if obj.is_active else '停用'}", "is_active": obj.is_active}
