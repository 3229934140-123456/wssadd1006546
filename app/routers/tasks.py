from typing import List, Optional, Tuple
from datetime import datetime, date, time
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy import or_, and_, func

from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import (
    CallbackTask, TaskStatus, CallResult, User, UserRole,
    Patient, TreatmentRecord, CallbackRule, Store, ReviewStatus
)
from ..schemas.task import (
    GenerateTasksRequest, ReassignTaskRequest, HandleTaskRequest,
    CompleteDoctorReviewRequest, CallbackTaskResponse, TaskListResponse,
    TaskGroup, TaskGroupStats, GroupedTaskResponse, AssignmentReasonDetail,
    NurseFollowupRequest, ReviewCollaborationStats
)
from ..services.task_pool_service import (
    generate_tasks_for_store, generate_tasks_by_record_ids,
    check_and_mark_timeout_tasks, apply_overdue_filter, FINISHED_STATUSES
)
from ..services.assignment_service import (
    auto_assign_pending_tasks, assign_task_to_user, pick_doctor_for_task,
    find_assignable_users, get_assignment_reason_detail
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


def _get_pending_statuses() -> list:
    return [
        TaskStatus.PENDING,
        TaskStatus.ASSIGNED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.ABNORMAL,
        TaskStatus.DOCTOR_REVIEW,
        TaskStatus.TIMEOUT,
    ]


def _apply_default_filter(
    query,
    status: Optional[TaskStatus],
    scheduled_date_from: Optional[str],
    scheduled_date_to: Optional[str],
    scheduled_time_from: Optional[str] = None,
    scheduled_time_to: Optional[str] = None,
):
    has_explicit_filter = (
        status is not None
        or scheduled_date_from is not None
        or scheduled_date_to is not None
        or scheduled_time_from is not None
        or scheduled_time_to is not None
    )
    if not has_explicit_filter:
        now = datetime.utcnow()
        today = now.date()
        current_time = now.time()
        query = query.filter(
            (
                (CallbackTask.status.in_(_get_pending_statuses()))
                & (CallbackTask.scheduled_date <= today)
                & (
                    (CallbackTask.scheduled_date < today)
                    | (
                        (CallbackTask.scheduled_date == today)
                        & (
                            (CallbackTask.scheduled_time.is_(None))
                            | (CallbackTask.scheduled_time <= current_time)
                        )
                    )
                )
            )
            | (CallbackTask.status == TaskStatus.DOCTOR_REVIEW)
        )
    return query


def _apply_base_scope(
    query,
    current_user: User,
    store_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
):
    if current_user.role == UserRole.CALL_AGENT:
        query = query.filter(CallbackTask.assigned_user_id == current_user.id)
    elif current_user.role == UserRole.STORE_NURSE:
        query = query.filter(
            (CallbackTask.assigned_user_id == current_user.id)
            | (CallbackTask.store_id == current_user.store_id)
        )
    elif current_user.role == UserRole.DOCTOR:
        query = query.filter(
            (CallbackTask.assigned_user_id == current_user.id)
            | (
                (CallbackTask.status == TaskStatus.DOCTOR_REVIEW)
                & (CallbackTask.store_id == current_user.store_id)
            )
        )
    elif current_user.role != UserRole.ADMIN and current_user.store_id:
        query = query.filter(CallbackTask.store_id == current_user.store_id)

    if store_id and (current_user.role == UserRole.ADMIN or not current_user.store_id):
        query = query.filter(CallbackTask.store_id == store_id)
    if assigned_user_id:
        query = query.filter(CallbackTask.assigned_user_id == assigned_user_id)
    return query


def _apply_common_filters(
    query,
    status: Optional[TaskStatus] = None,
    patient_keyword: Optional[str] = None,
    scheduled_date_from: Optional[str] = None,
    scheduled_date_to: Optional[str] = None,
    scheduled_time_from: Optional[str] = None,
    scheduled_time_to: Optional[str] = None,
    treatment_type_id: Optional[int] = None,
    is_overdue: Optional[bool] = None,
):
    from datetime import datetime

    if status:
        query = query.filter(CallbackTask.status == status)
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
    if scheduled_time_from:
        try:
            t = datetime.strptime(scheduled_time_from, "%H:%M:%S").time()
            query = query.filter(CallbackTask.scheduled_time >= t)
        except:
            pass
    if scheduled_time_to:
        try:
            t = datetime.strptime(scheduled_time_to, "%H:%M:%S").time()
            query = query.filter(CallbackTask.scheduled_time <= t)
        except:
            pass
    if treatment_type_id:
        query = query.join(TreatmentRecord).filter(
            TreatmentRecord.treatment_type_id == treatment_type_id
        )
    if is_overdue:
        query = apply_overdue_filter(query)
    return query


def _apply_group_filter(
    query,
    group: Optional[TaskGroup],
    now: Optional[datetime] = None
) -> Tuple:
    if now is None:
        now = datetime.utcnow()
    today = now.date()
    current_time = now.time()

    base_query = query.filter(
        (CallbackTask.status.in_(_get_pending_statuses()))
        & (CallbackTask.status.not_in(FINISHED_STATUSES))
    )

    if group == TaskGroup.OVERDUE:
        query = apply_overdue_filter(base_query, now)
    elif group == TaskGroup.NOW:
        query = base_query.filter(
            (
                (CallbackTask.scheduled_date < today)
                | (
                    (CallbackTask.scheduled_date == today)
                    & (
                        (CallbackTask.scheduled_time.is_(None))
                        | (CallbackTask.scheduled_time <= current_time)
                    )
                )
            )
            & (
                (CallbackTask.due_time.is_(None))
                | (CallbackTask.due_time >= now)
            )
        )
    elif group == TaskGroup.LATER:
        query = base_query.filter(
            (CallbackTask.scheduled_date == today)
            & (CallbackTask.scheduled_time > current_time)
        )
    else:
        return base_query

    return query


@router.get("/grouped", response_model=GroupedTaskResponse)
def get_grouped_tasks(
    group: Optional[TaskGroup] = Query(TaskGroup.NOW),
    store_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    patient_keyword: Optional[str] = None,
    treatment_type_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    now = datetime.utcnow()
    today = now.date()
    current_time = now.time()

    base_query = db.query(CallbackTask).options(
        joinedload(CallbackTask.patient),
        joinedload(CallbackTask.store),
        joinedload(CallbackTask.rule),
        joinedload(CallbackTask.treatment_record).joinedload(TreatmentRecord.treatment_type),
        joinedload(CallbackTask.assigned_user),
    )

    base_query = _apply_base_scope(base_query, current_user, store_id, assigned_user_id)
    base_query = _apply_common_filters(
        base_query,
        patient_keyword=patient_keyword,
        treatment_type_id=treatment_type_id,
    )

    pending_query = base_query.filter(
        (CallbackTask.status.in_(_get_pending_statuses()))
        & (CallbackTask.status.not_in(FINISHED_STATUSES))
    )

    now_count_query = pending_query.filter(
        (
            (CallbackTask.scheduled_date < today)
            | (
                (CallbackTask.scheduled_date == today)
                & (
                    (CallbackTask.scheduled_time.is_(None))
                    | (CallbackTask.scheduled_time <= current_time)
                )
            )
        )
        & (
            (CallbackTask.due_time.is_(None))
            | (CallbackTask.due_time >= now)
        )
    )
    now_count = now_count_query.count()

    later_count = pending_query.filter(
        (CallbackTask.scheduled_date == today)
        & (CallbackTask.scheduled_time > current_time)
    ).count()

    overdue_count = apply_overdue_filter(pending_query, now).count()

    list_query = _apply_group_filter(base_query, group, now)
    list_query = _apply_common_filters(
        list_query,
        patient_keyword=patient_keyword,
        treatment_type_id=treatment_type_id,
    )

    total = list_query.count()
    items = list_query.order_by(
        CallbackTask.priority.desc(),
        CallbackTask.scheduled_date.asc(),
        CallbackTask.scheduled_time.asc().nullslast(),
        CallbackTask.created_at.asc()
    ).offset((page - 1) * page_size).limit(page_size).all()

    stats = TaskGroupStats(
        now_count=now_count,
        later_count=later_count,
        overdue_count=overdue_count,
        active_group=group
    )
    tasks = TaskListResponse(items=items, total=total, page=page, page_size=page_size)
    return GroupedTaskResponse(stats=stats, tasks=tasks)


@router.get("", response_model=TaskListResponse)
def list_tasks(
    status: Optional[TaskStatus] = None,
    store_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    patient_keyword: Optional[str] = None,
    scheduled_date_from: Optional[str] = None,
    scheduled_date_to: Optional[str] = None,
    scheduled_time_from: Optional[str] = None,
    scheduled_time_to: Optional[str] = None,
    treatment_type_id: Optional[int] = None,
    is_overdue: Optional[bool] = None,
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
        joinedload(CallbackTask.reviewed_by),
    )

    query = _apply_base_scope(query, current_user, store_id, assigned_user_id)
    query = _apply_default_filter(query, status, scheduled_date_from, scheduled_date_to,
                                  scheduled_time_from, scheduled_time_to)
    query = _apply_common_filters(
        query,
        status=status,
        patient_keyword=patient_keyword,
        scheduled_date_from=scheduled_date_from,
        scheduled_date_to=scheduled_date_to,
        scheduled_time_from=scheduled_time_from,
        scheduled_time_to=scheduled_time_to,
        treatment_type_id=treatment_type_id,
        is_overdue=is_overdue,
    )

    total = query.count()
    items = query.order_by(
        CallbackTask.priority.desc(),
        CallbackTask.scheduled_date.asc(),
        CallbackTask.scheduled_time.asc().nullslast(),
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
        joinedload(CallbackTask.reviewed_by),
    ).filter(CallbackTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current_user.role == UserRole.CALL_AGENT:
        is_original_handler = (
            task.handled_by_id == current_user.id
            or task.reassigned_from_id == current_user.id
        )
        if task.assigned_user_id != current_user.id and not is_original_handler:
            raise HTTPException(status_code=403, detail="无权查看他人任务")
    if current_user.role == UserRole.DOCTOR:
        can_see = (
            task.assigned_user_id == current_user.id
            or (
                task.status in [TaskStatus.DOCTOR_REVIEW, TaskStatus.DOCTOR_REVIEWED]
                and task.store_id == current_user.store_id
            )
        )
        if not can_see:
            raise HTTPException(status_code=403, detail="无权查看其他门店的复核任务")
    elif current_user.role not in [UserRole.ADMIN, UserRole.STORE_NURSE] and task.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="无权查看其他门店任务")
    return task


@router.get("/{task_id}/assignment-reason", response_model=AssignmentReasonDetail)
def get_task_assignment_reason(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STORE_NURSE))
):
    task = db.query(CallbackTask).options(
        joinedload(CallbackTask.patient),
    ).filter(CallbackTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current_user.role != UserRole.ADMIN and task.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="无权查看其他门店任务")

    detail, is_snapshot = get_assignment_reason_detail(db, task)
    detail["is_snapshot"] = is_snapshot
    return detail


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
    if task.status not in [TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.TIMEOUT]:
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
    if task.status not in [TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.TIMEOUT]:
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
        task.review_status = ReviewStatus.PENDING_DOCTOR
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
    task.doctor_review_notes = req.review_notes
    task.doctor_conclusion = req.doctor_conclusion
    task.suggested_review_date = req.suggested_review_date
    task.reviewed_by_id = current_user.id
    task.reviewed_at = datetime.utcnow()
    task.handled_by_id = current_user.id
    task.handled_at = datetime.utcnow()

    if req.doctor_conclusion in ["正常观察", "无需复诊"] or not req.suggested_review_date:
        task.review_status = ReviewStatus.CLOSED
    else:
        task.review_status = ReviewStatus.PENDING_FOLLOWUP

    summary_parts = []
    if task.callback_notes:
        summary_parts.append(task.callback_notes)
    summary_parts.append("\n\n【医生复核意见】")
    if req.doctor_conclusion:
        summary_parts.append(f"处理结论：{req.doctor_conclusion}")
    if req.suggested_review_date:
        summary_parts.append(f"建议复诊：{req.suggested_review_date.strftime('%Y-%m-%d')}")
    summary_parts.append(f"医生意见：{req.review_notes}")
    task.callback_notes = "\n".join(summary_parts)

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
    return [{"id": u.id, "real_name": u.real_name, "full_name": u.real_name or u.real_name,
             "username": u.username, "role": u.role.value, "store_id": u.store_id} for u in users]


@router.get("/review-collaboration/stats", response_model=ReviewCollaborationStats)
def get_review_collaboration_stats(
    store_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CallbackTask).filter(CallbackTask.is_abnormal == True)
    if current_user.role != UserRole.ADMIN and current_user.store_id:
        store_id = current_user.store_id
    if store_id:
        query = query.filter(CallbackTask.store_id == store_id)
    from .stats import parse_date
    sd = parse_date(start_date)
    ed = parse_date(end_date)
    if sd: query = query.filter(CallbackTask.scheduled_date >= sd)
    if ed: query = query.filter(CallbackTask.scheduled_date <= ed)

    total = query.count()
    pending_doctor = query.filter(
        (CallbackTask.status == TaskStatus.DOCTOR_REVIEW)
        | (CallbackTask.review_status == ReviewStatus.PENDING_DOCTOR)
    ).count()
    doctor_advised = query.filter(CallbackTask.review_status == ReviewStatus.DOCTOR_ADVISED).count()
    doctor_advised += query.filter(
        (CallbackTask.status == TaskStatus.DOCTOR_REVIEWED)
        & (CallbackTask.review_status.is_(None))
    ).count()
    pending_followup = query.filter(CallbackTask.review_status == ReviewStatus.PENDING_FOLLOWUP).count()
    closed = query.filter(CallbackTask.review_status == ReviewStatus.CLOSED).count()

    closure_rate = round(closed * 100.0 / total, 2) if total > 0 else 0.0

    return ReviewCollaborationStats(
        pending_doctor=pending_doctor,
        doctor_advised=doctor_advised,
        pending_followup=pending_followup,
        closed=closed,
        total=total,
        closure_rate=closure_rate
    )


@router.get("/review-collaboration", response_model=TaskListResponse)
def list_review_collaboration_tasks(
    review_status: Optional[ReviewStatus] = None,
    store_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    patient_keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CallbackTask).options(
        joinedload(CallbackTask.patient),
        joinedload(CallbackTask.store),
        joinedload(CallbackTask.assigned_user),
        joinedload(CallbackTask.reviewed_by),
        joinedload(CallbackTask.followup_by),
        joinedload(CallbackTask.treatment_record).joinedload(TreatmentRecord.treatment_type),
    ).filter(CallbackTask.is_abnormal == True)

    if current_user.role == UserRole.CALL_AGENT:
        query = query.filter(
            (CallbackTask.assigned_user_id == current_user.id)
            | (CallbackTask.handled_by_id == current_user.id)
            | (CallbackTask.reassigned_from_id == current_user.id)
        )
    elif current_user.role == UserRole.DOCTOR:
        query = query.filter(
            (CallbackTask.assigned_user_id == current_user.id)
            | (CallbackTask.reviewed_by_id == current_user.id)
            | (
                (CallbackTask.status.in_([TaskStatus.DOCTOR_REVIEW, TaskStatus.DOCTOR_REVIEWED]))
                & (CallbackTask.store_id == current_user.store_id)
            )
        )
    elif current_user.role != UserRole.ADMIN and current_user.store_id:
        store_id = current_user.store_id

    if store_id:
        query = query.filter(CallbackTask.store_id == store_id)

    if review_status:
        if review_status == ReviewStatus.DOCTOR_ADVISED:
            query = query.filter(
                (CallbackTask.review_status == ReviewStatus.DOCTOR_ADVISED)
                | (
                    (CallbackTask.status == TaskStatus.DOCTOR_REVIEWED)
                    & (CallbackTask.review_status.is_(None))
                )
            )
        elif review_status == ReviewStatus.PENDING_DOCTOR:
            query = query.filter(
                (CallbackTask.review_status == ReviewStatus.PENDING_DOCTOR)
                | (CallbackTask.status == TaskStatus.DOCTOR_REVIEW)
            )
        else:
            query = query.filter(CallbackTask.review_status == review_status)

    from .stats import parse_date
    sd = parse_date(start_date)
    ed = parse_date(end_date)
    if sd: query = query.filter(CallbackTask.scheduled_date >= sd)
    if ed: query = query.filter(CallbackTask.scheduled_date <= ed)
    if patient_keyword:
        like = f"%{patient_keyword}%"
        query = query.join(Patient).filter(
            or_(Patient.name.like(like), Patient.phone.like(like))
        )

    total = query.count()
    items = query.order_by(
        CallbackTask.priority.desc(),
        CallbackTask.created_at.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()

    return TaskListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("/nurse-followup", response_model=CallbackTaskResponse)
def nurse_followup(
    req: NurseFollowupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.STORE_NURSE, UserRole.ADMIN))
):
    task = db.query(CallbackTask).filter(CallbackTask.id == req.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current_user.role != UserRole.ADMIN and task.store_id != current_user.store_id:
        raise HTTPException(status_code=403, detail="无权跟进其他门店任务")
    if task.status not in [TaskStatus.DOCTOR_REVIEWED, TaskStatus.DOCTOR_REVIEW]:
        raise HTTPException(status_code=400, detail="任务尚未完成医生复核，无法跟进")

    task.nurse_followup_notes = req.followup_notes
    task.followup_result = req.followup_result
    task.followup_by_id = current_user.id
    task.followup_at = datetime.utcnow()
    if req.actual_review_date:
        task.actual_review_date = req.actual_review_date

    if req.close_review or req.followup_result in ["已复诊", "无需复诊", "已失联"]:
        task.review_status = ReviewStatus.CLOSED
    else:
        task.review_status = ReviewStatus.PENDING_FOLLOWUP

    if task.callback_notes:
        task.callback_notes = (
            task.callback_notes
            + f"\n\n【门店护士跟进】\n跟进结果：{req.followup_result or '未填写'}\n"
            + (f"实际复诊：{req.actual_review_date.strftime('%Y-%m-%d')}\n" if req.actual_review_date else "")
            + f"跟进说明：{req.followup_notes}"
        )

    db.commit()
    db.refresh(task)
    return task

