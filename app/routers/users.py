from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_current_active_admin, require_roles
from ..models import User, UserRole
from ..schemas.user import UserCreate, UserUpdate, UserResponse
from ..security import hash_password

router = APIRouter(prefix="/api/users", tags=["用户管理"])


@router.get("", response_model=List[UserResponse])
def list_users(
    role: Optional[UserRole] = None,
    store_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(User)
    if current_user.role != UserRole.ADMIN and current_user.store_id:
        query = query.filter(User.store_id == current_user.store_id)
    if role:
        query = query.filter(User.role == role)
    if store_id:
        query = query.filter(User.store_id == store_id)
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items


@router.post("", response_model=UserResponse)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    existing = db.query(User).filter(User.username == user_data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    if user_data.store_id is None and user_data.role in [UserRole.STORE_NURSE, UserRole.DOCTOR]:
        raise HTTPException(status_code=400, detail="门店护士和医生必须指定门店")
    db_user = User(
        username=user_data.username,
        real_name=user_data.real_name,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        role=user_data.role,
        store_id=user_data.store_id,
        is_active=user_data.is_active,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if current_user.role != UserRole.ADMIN and user.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="无权查看其他门店用户")
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    update_data = user_data.model_dump(exclude_unset=True)
    if "password" in update_data:
        update_data["hashed_password"] = hash_password(update_data.pop("password"))
    for key, value in update_data.items():
        setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_admin)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    db.delete(user)
    db.commit()
    return {"message": "删除成功"}
