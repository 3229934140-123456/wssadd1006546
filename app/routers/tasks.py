from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, and_

from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import (
    CallbackTask, TaskStatus, CallResult, User, UserRole,
    Patient, TreatmentRecord, CallbackRule, Store
)
from ..schemas.task import (
    GenerateTasksRequest, ReassignTaskRequest, HandleTaskRequest,
    CompleteDoctorReviewRequest, CallbackTaskResponse, TaskListResponse
)
from ..services.task_pool_service import (
    generate_tasks_for_store, generate_tasks_by_record_ids,
    check_and_mark_timeout_tasks
)
from ..services.assignment_service import (
    auto_assign_pending_tasks, assign_task_to_user, pick_doctor_for_task, find_assignable_users
)
from ..services.keyword_service import (
    parse_keywords, detect_abnormal_keywords, DEFAULT_ABNORMAL_KEYWORDS
)

router = APIRouter(prefix="/api/tasks", tags=["坐席任务"])


@router.post("/generate", response_model=List[CallbackTaskResponse])
def generate_tasks(
    req: GenerateTasksRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STORE_NURSE))
):
    if current_user.role != UserRole.ADMIN and current_user.store_id:
        req.store_id = current_user.store_id

    if req.treatment_record_ids and len(req.treatment_record_ids) > 0:
        tasks = generate_tasks_by_record_ids(db, req.treatment_record_ids)
    else:
        tasks = generate_tasks_for_store(db, req.store_id)

    auto_assign_pending_tasks(db)
    return tasks


@router.post("/auto-assign")
def run_auto_assign(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STORE_NURSE))
):
    count = auto_assign_pending_tasks(db, limit)
    return {"message": f"已自动分派 {count} 个任务", "assigned_count": count}


@router.post("/check-timeout")
def run_check_timeout(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN))
):
    count = check_and_mark_timeout_tasks(db)
    return {"message": f"已标记 {count} 个超时任务", "timeout_count": count}


@router.get("", response_model=TaskListResponse)
def list_tasks(
    status: Optional[TaskStatus] = None,
    store_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    patient_keyword: Optional[str] = None,
    scheduled_date_from: Optional[str] = None,
    scheduled_date_to: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CallbackTask).options(
        joinedload(CallbackTask.patient),
        joinedload(CallbackTask.store),
        joinedload(CallbackTask.rule),
        joinedload(CallbackTask.treatment_record).joinedload(TreatmentRecord.treatment_type),
        joinedload(CallbackTask.assigned_user),
    )

    if current_user.role == UserRole.CALL_AGENT:
        query = query.filter(CallbackTask.assigned_user_id == current_user.id)
    elif current_user.role == UserRole.DOCTOR:
        query = query.filter(
            (CallbackTask.assigned_user_id == current_user.id) |
            (CallbackTask.status == TaskStatus.DOCTOR_REVIEW)
        )
    elif current_user.role != UserRole.ADMIN and current_user.store_id:
        query = query.filter(CallbackTask.store_id == current_user.store_id)

    if status:
        query = query.filter(CallbackTask.status == status)
    if store_id and (current_user.role == UserRole.ADMIN or not current_user.store_id):
        query = query.filter(CallbackTask.store_id == store_id)
    if assigned_user_id:
        query = query.filter(CallbackTask.assigned_user_id == assigned_user_id)
    if patient_keyword:
        like = f"%{patient_keyword}%"
        query = query.join(Patient).filter(
            or_(Patient.name.like(like), Patient.phone.like(like))
        )
    if scheduled_date_from:
        try:
            d = datetime.strptime(scheduled_date_from, "%Y-%m-%d").date()
            query = query.filter(CallbackTask.scheduled_date >= d)
        except:
            pass
    if scheduled_date_to:
        try:
            d = datetime.strptime(scheduled_date_to, "%Y-%m-%d").date()
            query = query.filter(CallbackTask.scheduled_date <= d)
        except:
            pass

    total = query.count()
    items = query.order_by(
        CallbackTask.priority.desc(),
        CallbackTask.scheduled_date.asc(),
        CallbackTask.created_at.asc()
    ).offset((page - 1) * page_size).limit(page_size).all()

    return TaskListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{task_id}", response_model=CallbackTaskResponse)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    task = db.query(CallbackTask).options(
        joinedload(CallbackTask.patient),
        joinedload(CallbackTask.store),
        joinedload(CallbackTask.rule),
        joinedload(CallbackTask.treatment_record).joinedload(TreatmentRecord.treatment_type),
        joinedload(CallbackTask.assigned_user),
        joinedload(CallbackTask.handled_by),
    ).filter(CallbackTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current_user.role == UserRole.CALL_AGENT and task.assigned_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看他人任务")
    if current_user.role not in [UserRole.ADMIN, UserRole.STORE_NURSE] and task.store_id != current_user.store_id:
        if not (current_user.role == UserRole.DOCTOR and task.status == TaskStatus.DOCTOR_REVIEW):
            raise HTTPException(status_code=403, detail="无权查看其他门店任务")
    return task


@router.post("/{task_id}/start", response_model=CallbackTaskResponse)
def start_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CALL_AGENT, UserRole.STORE_NURSE, UserRole.DOCTOR))
):
    task = db.query(CallbackTask).filter(CallbackTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.assigned_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能开始分配给自己的任务")
    if task.status not in [TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS]:
        raise HTTPException(status_code=400, detail=f"任务状态为 {task.status.value}，无法开始")
    task.status = TaskStatus.IN_PROGRESS
    db.commit()
    db.refresh(task)
    return task


@router.post("/handle", response_model=CallbackTaskResponse)
def handle_task(
    req: HandleTaskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.CALL_AGENT, UserRole.STORE_NURSE))
):
    task = db.query(CallbackTask).options(
        joinedload(CallbackTask.rule)
    ).filter(CallbackTask.id == req.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.assigned_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能处理分配给自己的任务")
    if task.status not in [TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS]:
        raise HTTPException(status_code=400, detail=f"任务状态为 {task.status.value}，无法处理")

    task.call_result = req.call_result
    task.call_duration_seconds = req.call_duration_seconds or 0
    task.callback_notes = req.callback_notes
    task.handled_by_id = current_user.id
    task.handled_at = datetime.utcnow()

    abnormal_hits = []
    keywords_str = None
    if task.rule:
        keywords_str = task.rule.abnormal_keywords
    if not keywords_str:
        keywords_str = DEFAULT_ABNORMAL_KEYWORDS
    keywords = parse_keywords(keywords_str)
    if req.callback_notes:
        hits = detect_abnormal_keywords(req.callback_notes, keywords)
        abnormal_hits.extend(hits)

    need_doctor_review = req.escalate_to_doctor or len(abnormal_hits) > 0

    if need_doctor_review:
        task.status = TaskStatus.DOCTOR_REVIEW
        task.is_abnormal = True
        task.abnormal_keywords_hit = ",".join(abnormal_hits) if abnormal_hits else None
        doctor = pick_doctor_for_task(db, task.store_id)
        if doctor:
            task.assigned_user_id = doctor.id
            task.assigned_at = datetime.utcnow()
            task.reassigned_from_id = current_user.id
            task.reassigned_at = datetime.utcnow()
            task.reassigned_reason = "异常转医生复核" if abnormal_hits else "坐席主动提交复核"
    else:
        if req.call_result == CallResult.CONNECTED:
            task.status = TaskStatus.COMPLETED
        else:
            task.status = TaskStatus.ABNORMAL
            task.is_abnormal = True

    db.commit()
    db.refresh(task)
    return task


@router.post("/complete-doctor-review", response_model=CallbackTaskResponse)
def complete_doctor_review(
    req: CompleteDoctorReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.DOCTOR, UserRole.ADMIN))
):
    task = db.query(CallbackTask).filter(CallbackTask.id == req.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != TaskStatus.DOCTOR_REVIEW:
        raise HTTPException(status_code=400, detail="任务不是医生复核状态")
    if current_user.role == UserRole.DOCTOR and task.assigned_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="只能复核分配给自己的任务")

    task.status = TaskStatus.DOCTOR_REVIEWED
    task.handled_by_id = current_user.id
    task.handled_at = datetime.utcnow()
    if task.callback_notes:
        task.callback_notes = task.callback_notes + "\n\n【医生复核意见】\n" + req.review_notes
    else:
        task.callback_notes = "【医生复核意见】\n" + req.review_notes

    db.commit()
    db.refresh(task)
    return task


@router.post("/reassign", response_model=CallbackTaskResponse)
def reassign_task(
    req: ReassignTaskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STORE_NURSE))
):
    task = db.query(CallbackTask).filter(CallbackTask.id == req.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current_user.role != UserRole.ADMIN and task.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="无权转派其他门店任务")
    return assign_task_to_user(db, task, req.target_user_id, req.reason)


@router.get("/assignable-users", response_model=List)
def get_assignable_users(
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STORE_NURSE))
):
    if current_user.role != UserRole.ADMIN and current_user.store_id:
        store_id = current_user.store_id
    users = find_assignable_users(db, store_id)
    return [{"id": u.id, "real_name": u.real_name, "username": u.username, "role": u.role.value, "store_id": u.store_id} for u in users]
