from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_current_active_admin, require_roles
from ..models import Store, User, UserRole
from ..schemas.store import StoreCreate, StoreUpdate, StoreResponse

router = APIRouter(prefix="/api/stores", tags=["门店管理"])


@router.get("", response_model=List[StoreResponse])
def list_stores(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Store)
    if current_user.role != UserRole.ADMIN and current_user.store_id:
        query = query.filter(Store.id == current_user.store_id)
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items


@router.post("", response_model=StoreResponse)
def create_store(
    store_data: StoreCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    existing = db.query(Store).filter(Store.store_code == store_data.store_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="门店编码已存在")
    db_store = Store(**store_data.model_dump())
    db.add(db_store)
    db.commit()
    db.refresh(db_store)
    return db_store


@router.get("/{store_id}", response_model=StoreResponse)
def get_store(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="门店不存在")
    if current_user.role != UserRole.ADMIN and store.id != current_user.store_id:
        raise HTTPException(status_code=403, detail="无权查看其他门店信息")
    return store


@router.put("/{store_id}", response_model=StoreResponse)
def update_store(
    store_id: int,
    store_data: StoreUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="门店不存在")
    update_data = store_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(store, key, value)
    db.commit()
    db.refresh(store)
    return store


@router.delete("/{store_id}")
def delete_store(
    store_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail="门店不存在")
    db.delete(store)
    db.commit()
    return {"message": "删除成功"}
