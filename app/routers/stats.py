from typing import List, Optional
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_

from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import (
    CallbackTask, TaskStatus, Store, User, UserRole, Patient
)
from ..schemas.stats import (
    StatsOverview, StoreStats, UserStats, TimeoutTaskItem
)
from ..services.task_pool_service import (
    apply_overdue_filter, count_overdue_tasks
)

router = APIRouter(prefix="/api/stats", tags=["统计看板"])


def safe_div(a, b):
    if b == 0:
        return 0.0
    return round(a * 100.0 / b, 2)


@router.get("/overview", response_model=StatsOverview)
def get_stats_overview(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CallbackTask)
    if current_user.role != UserRole.ADMIN and current_user.store_id:
        store_id = current_user.store_id
    if store_id:
        query = query.filter(CallbackTask.store_id == store_id)

    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            query = query.filter(CallbackTask.scheduled_date >= start_dt)
        except:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            query = query.filter(CallbackTask.scheduled_date <= end_dt)
        except:
            pass

    total = query.count()

    status_counts = {}
    for status in TaskStatus:
        status_counts[status] = query.filter(CallbackTask.status == status).count()

    done_total = status_counts.get(TaskStatus.COMPLETED, 0) + status_counts.get(TaskStatus.DOCTOR_REVIEWED, 0)
    abnormal_total = status_counts.get(TaskStatus.ABNORMAL, 0) + status_counts.get(TaskStatus.DOCTOR_REVIEW, 0) + status_counts.get(TaskStatus.DOCTOR_REVIEWED, 0)

    timeout_count = count_overdue_tasks(db, store_id=store_id, base_query=query)

    overview = StatsOverview(
        total_tasks=total,
        pending_tasks=status_counts.get(TaskStatus.PENDING, 0),
        in_progress_tasks=status_counts.get(TaskStatus.IN_PROGRESS, 0) + status_counts.get(TaskStatus.ASSIGNED, 0),
        completed_tasks=done_total,
        completion_rate=safe_div(done_total, total),
        abnormal_tasks=abnormal_total,
        abnormal_rate=safe_div(abnormal_total, total),
        timeout_tasks=timeout_count,
        doctor_review_tasks=status_counts.get(TaskStatus.DOCTOR_REVIEW, 0),
        doctor_reviewed_tasks=status_counts.get(TaskStatus.DOCTOR_REVIEWED, 0),
    )
    return overview


@router.get("/by-store", response_model=List[StoreStats])
def get_stats_by_store(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    stores = db.query(Store).all()
    if store_id:
        stores = [s for s in stores if s.id == store_id]

    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        except:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        except:
            pass

    results = []
    for store in stores:
        query = db.query(CallbackTask).filter(CallbackTask.store_id == store.id)
        if start_dt:
            query = query.filter(CallbackTask.scheduled_date >= start_dt)
        if end_dt:
            query = query.filter(CallbackTask.scheduled_date <= end_dt)

        total = query.count()
        completed = query.filter(
            CallbackTask.status.in_([TaskStatus.COMPLETED, TaskStatus.DOCTOR_REVIEWED])
        ).count()
        abnormal = query.filter(CallbackTask.is_abnormal == True).count()
        timeout = count_overdue_tasks(db, store_id=store.id, base_query=query)
        doctor_review = query.filter(
            CallbackTask.status.in_([TaskStatus.DOCTOR_REVIEW, TaskStatus.DOCTOR_REVIEWED])
        ).count()

        stat = StoreStats(
            store_id=store.id,
            store_name=store.store_name,
            total_tasks=total,
            completed_tasks=completed,
            completion_rate=safe_div(completed, total),
            abnormal_tasks=abnormal,
            abnormal_rate=safe_div(abnormal, total),
            timeout_tasks=timeout,
            doctor_review_tasks=doctor_review,
        )
        results.append(stat)

    results.sort(key=lambda x: x.completion_rate, reverse=True)
    return results


@router.get("/by-user", response_model=List[UserStats])
def get_stats_by_user(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query_users = db.query(User).filter(User.is_active == True)
    if current_user.role != UserRole.ADMIN and current_user.store_id:
        store_id = current_user.store_id
    if store_id:
        query_users = query_users.filter(User.store_id == store_id)

    users = query_users.filter(User.role.in_([UserRole.CALL_AGENT, UserRole.STORE_NURSE, UserRole.DOCTOR])).all()

    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        except:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        except:
            pass

    results = []
    for user in users:
        query = db.query(CallbackTask).filter(
            (CallbackTask.assigned_user_id == user.id) |
            (CallbackTask.handled_by_id == user.id)
        )
        if start_dt:
            query = query.filter(CallbackTask.scheduled_date >= start_dt)
        if end_dt:
            query = query.filter(CallbackTask.scheduled_date <= end_dt)

        total = query.count()
        completed = query.filter(
            (CallbackTask.handled_by_id == user.id) &
            (CallbackTask.status.in_([TaskStatus.COMPLETED, TaskStatus.DOCTOR_REVIEWED]))
        ).count()
        abnormal = query.filter(
            (CallbackTask.handled_by_id == user.id) &
            (CallbackTask.is_abnormal == True)
        ).count()
        durations = db.query(func.avg(CallbackTask.call_duration_seconds)).filter(
            (CallbackTask.handled_by_id == user.id) &
            (CallbackTask.call_duration_seconds > 0)
        ).scalar()

        stat = UserStats(
            user_id=user.id,
            user_name=user.real_name,
            role=user.role.value,
            total_tasks=total,
            completed_tasks=completed,
            completion_rate=safe_div(completed, total),
            abnormal_tasks=abnormal,
            avg_call_duration=round(durations or 0, 1),
        )
        results.append(stat)

    results.sort(key=lambda x: x.completion_rate, reverse=True)
    return results


@router.get("/timeout-list", response_model=List[TimeoutTaskItem])
def get_timeout_tasks_list(
    store_id: Optional[int] = None,
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CallbackTask).options(
        joinedload(CallbackTask.patient),
        joinedload(CallbackTask.store),
    )

    query = apply_overdue_filter(query)

    if current_user.role != UserRole.ADMIN and current_user.store_id:
        store_id = current_user.store_id
    if store_id:
        query = query.filter(CallbackTask.store_id == store_id)

    timeout_items = query.order_by(CallbackTask.due_time.asc()).limit(limit).all()

    results = []
    now = datetime.utcnow()
    for t in timeout_items:
        overdue_hours = 0
        if t.due_time:
            overdue_hours = round((now - t.due_time).total_seconds() / 3600, 1)
        item = TimeoutTaskItem(
            task_id=t.id,
            task_no=t.task_no,
            patient_name=t.patient.name if t.patient else "未知",
            phone=t.patient.phone if t.patient else "",
            store_name=t.store.store_name if t.store else "未知",
            scheduled_date=t.scheduled_date,
            status=t.status.value,
            overdue_hours=overdue_hours,
        )
        results.append(item)
    return results
