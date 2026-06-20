from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload

from ..database import get_db
from ..deps import get_current_user, get_current_active_admin
from ..models import TreatmentType, TreatmentRecord, Patient, User, UserRole
from ..schemas.treatment import (
    TreatmentTypeCreate, TreatmentTypeUpdate, TreatmentTypeResponse,
    TreatmentRecordCreate, TreatmentRecordUpdate, TreatmentRecordResponse
)

router = APIRouter(prefix="/api", tags=["治疗管理"])


@router.get("/treatment-types", response_model=List[TreatmentTypeResponse])
def list_treatment_types(
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(TreatmentType)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter((TreatmentType.type_name.like(like)) | (TreatmentType.type_code.like(like)))
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items


@router.post("/treatment-types", response_model=TreatmentTypeResponse)
def create_treatment_type(
    data: TreatmentTypeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    existing = db.query(TreatmentType).filter(TreatmentType.type_code == data.type_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="治疗类型编码已存在")
    obj = TreatmentType(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/treatment-types/{type_id}", response_model=TreatmentTypeResponse)
def get_treatment_type(
    type_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    obj = db.query(TreatmentType).filter(TreatmentType.id == type_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="治疗类型不存在")
    return obj


@router.put("/treatment-types/{type_id}", response_model=TreatmentTypeResponse)
def update_treatment_type(
    type_id: int,
    data: TreatmentTypeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    obj = db.query(TreatmentType).filter(TreatmentType.id == type_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="治疗类型不存在")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/treatment-types/{type_id}")
def delete_treatment_type(
    type_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    obj = db.query(TreatmentType).filter(TreatmentType.id == type_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="治疗类型不存在")
    db.delete(obj)
    db.commit()
    return {"message": "删除成功"}


@router.get("/treatment-records", response_model=List[TreatmentRecordResponse])
def list_treatment_records(
    patient_id: Optional[int] = None,
    store_id: Optional[int] = None,
    treatment_type_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(TreatmentRecord).options(
        joinedload(TreatmentRecord.treatment_type),
        joinedload(TreatmentRecord.patient)
    )
    if current_user.role != UserRole.ADMIN and current_user.store_id:
        query = query.join(Patient).filter(Patient.store_id == current_user.store_id)
    elif store_id:
        query = query.join(Patient).filter(Patient.store_id == store_id)
    if patient_id:
        query = query.filter(TreatmentRecord.patient_id == patient_id)
    if treatment_type_id:
        query = query.filter(TreatmentRecord.treatment_type_id == treatment_type_id)
    total = query.count()
    items = query.order_by(TreatmentRecord.treatment_date.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return items


@router.post("/treatment-records", response_model=TreatmentRecordResponse)
def create_treatment_record(
    data: TreatmentRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    patient = db.query(Patient).filter(Patient.id == data.patient_id).first()
    if not patient:
        raise HTTPException(status_code=400, detail="患者不存在")
    if current_user.role != UserRole.ADMIN and current_user.store_id and patient.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="只能为本门店患者创建治疗记录")
    ttype = db.query(TreatmentType).filter(TreatmentType.id == data.treatment_type_id).first()
    if not ttype:
        raise HTTPException(status_code=400, detail="治疗类型不存在")
    obj = TreatmentRecord(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/treatment-records/{record_id}", response_model=TreatmentRecordResponse)
def get_treatment_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    obj = db.query(TreatmentRecord).options(
        joinedload(TreatmentRecord.treatment_type),
        joinedload(TreatmentRecord.patient)
    ).filter(TreatmentRecord.id == record_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="治疗记录不存在")
    if current_user.role != UserRole.ADMIN and current_user.store_id and obj.patient.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="无权查看其他门店治疗记录")
    return obj


@router.put("/treatment-records/{record_id}", response_model=TreatmentRecordResponse)
def update_treatment_record(
    record_id: int,
    data: TreatmentRecordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    obj = db.query(TreatmentRecord).filter(TreatmentRecord.id == record_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="治疗记录不存在")
    patient = db.query(Patient).filter(Patient.id == obj.patient_id).first()
    if current_user.role != UserRole.ADMIN and current_user.store_id and patient and patient.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="无权修改其他门店治疗记录")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/treatment-records/{record_id}")
def delete_treatment_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    obj = db.query(TreatmentRecord).filter(TreatmentRecord.id == record_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="治疗记录不存在")
    db.delete(obj)
    db.commit()
    return {"message": "删除成功"}
