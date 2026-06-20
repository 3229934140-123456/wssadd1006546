from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import Patient, Store, User, UserRole
from ..schemas.patient import PatientCreate, PatientUpdate, PatientResponse

router = APIRouter(prefix="/api/patients", tags=["患者管理"])


@router.get("", response_model=List[PatientResponse])
def list_patients(
    store_id: Optional[int] = None,
    risk_level: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Patient)
    if current_user.role != UserRole.ADMIN and current_user.store_id:
        query = query.filter(Patient.store_id == current_user.store_id)
    elif store_id:
        query = query.filter(Patient.store_id == store_id)
    if risk_level:
        query = query.filter(Patient.risk_level == risk_level)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter((Patient.name.like(like)) | (Patient.phone.like(like)) | (Patient.patient_no.like(like)))
    total = query.count()
    items = query.order_by(Patient.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return items


@router.post("", response_model=PatientResponse)
def create_patient(
    patient_data: PatientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    existing = db.query(Patient).filter(Patient.patient_no == patient_data.patient_no).first()
    if existing:
        raise HTTPException(status_code=400, detail="患者编号已存在")
    if current_user.role != UserRole.ADMIN:
        if current_user.store_id and patient_data.store_id != current_user.store_id:
            raise HTTPException(status_code=403, detail="只能为当前门店创建患者")
    store = db.query(Store).filter(Store.id == patient_data.store_id).first()
    if not store:
        raise HTTPException(status_code=400, detail="门店不存在")
    db_patient = Patient(**patient_data.model_dump())
    db.add(db_patient)
    db.commit()
    db.refresh(db_patient)
    return db_patient


@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="患者不存在")
    if current_user.role != UserRole.ADMIN and patient.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="无权查看其他门店患者")
    return patient


@router.put("/{patient_id}", response_model=PatientResponse)
def update_patient(
    patient_id: int,
    patient_data: PatientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="患者不存在")
    if current_user.role != UserRole.ADMIN and patient.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="无权修改其他门店患者")
    update_data = patient_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(patient, key, value)
    db.commit()
    db.refresh(patient)
    return patient


@router.delete("/{patient_id}")
def delete_patient(
    patient_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    patient = db.query(Patient).filter(Patient.id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="患者不存在")
    db.delete(patient)
    db.commit()
    return {"message": "删除成功"}
