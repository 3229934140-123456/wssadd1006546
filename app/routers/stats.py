from typing import List, Optional
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, and_, or_
import io
import csv

from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import (
    CallbackTask, TaskStatus, Store, User, UserRole, Patient,
    TreatmentRecord, TreatmentType, CallbackRule, ReviewStatus
)
from ..schemas.stats import (
    StatsOverview, StoreStats, UserStats, TimeoutTaskItem,
    AbnormalTaskItem, StatsFilterOptions, RuleEffectItem
)
from ..services.task_pool_service import (
    apply_overdue_filter, count_overdue_tasks, FINISHED_STATUSES
)

router = APIRouter(prefix="/api/stats", tags=["统计看板"])


def safe_div(a, b):
    if b == 0:
        return 0.0
    return round(a * 100.0 / b, 2)


def parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except:
        return None


def apply_stats_filter(
    query,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    treatment_type_id: Optional[int] = None,
    current_user: Optional[User] = None,
    date_field: str = "scheduled_date",
):
    if current_user and current_user.role != UserRole.ADMIN and current_user.store_id:
        store_id = current_user.store_id

    if store_id:
        query = query.filter(CallbackTask.store_id == store_id)
    if assigned_user_id:
        query = query.filter(CallbackTask.assigned_user_id == assigned_user_id)
    if treatment_type_id:
        query = query.join(TreatmentRecord).filter(
            TreatmentRecord.treatment_type_id == treatment_type_id
        )

    start_dt = parse_date(start_date)
    end_dt = parse_date(end_date)
    date_col = CallbackTask.scheduled_date if date_field == "scheduled_date" else CallbackTask.created_at
    if start_dt:
        query = query.filter(date_col >= start_dt)
    if end_dt:
        query = query.filter(date_col <= end_dt)

    return query, start_dt, end_dt


@router.get("/filter-options", response_model=StatsFilterOptions)
def get_filter_options(
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    stores_query = db.query(Store)
    if current_user.role != UserRole.ADMIN and current_user.store_id:
        stores_query = stores_query.filter(Store.id == current_user.store_id)
    stores = [{"id": s.id, "store_name": s.store_name} for s in stores_query.all()]

    users_query = db.query(User).filter(User.is_active == True).filter(
        User.role.in_([UserRole.CALL_AGENT, UserRole.STORE_NURSE, UserRole.DOCTOR])
    )
    if current_user.role != UserRole.ADMIN and current_user.store_id:
        users_query = users_query.filter(User.store_id == current_user.store_id)
    elif store_id:
        users_query = users_query.filter(or_(User.store_id == store_id, User.store_id.is_(None)))
    users = [{"id": u.id, "full_name": u.real_name or u.real_name or u.username,
              "role": u.role.value, "store_id": u.store_id} for u in users_query.all()]

    treatment_types = [{"id": t.id, "type_name": t.type_name} for t in db.query(TreatmentType).all()]
    rules = [{"id": r.id, "rule_name": r.rule_name, "treatment_type_id": r.treatment_type_id,
              "call_window": r.call_window.value if r.call_window else None} for r in db.query(CallbackRule).all()]

    return StatsFilterOptions(
        stores=stores,
        users=users,
        treatment_types=treatment_types,
        rules=rules
    )


@router.get("/overview", response_model=StatsOverview)
def get_stats_overview(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    treatment_type_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CallbackTask)
    query, _, _ = apply_stats_filter(
        query, start_date, end_date, store_id,
        assigned_user_id, treatment_type_id, current_user
    )

    total = query.count()

    status_counts = {}
    for status in TaskStatus:
        status_counts[status] = query.filter(CallbackTask.status == status).count()

    done_total = status_counts.get(TaskStatus.COMPLETED, 0) + status_counts.get(TaskStatus.DOCTOR_REVIEWED, 0)
    abnormal_total = status_counts.get(TaskStatus.ABNORMAL, 0) + status_counts.get(TaskStatus.DOCTOR_REVIEW, 0) + status_counts.get(TaskStatus.DOCTOR_REVIEWED, 0)

    timeout_count = count_overdue_tasks(db, store_id=store_id, base_query=query)

    review_total_query = query.filter(CallbackTask.is_abnormal == True)
    rev_pending_doctor = review_total_query.filter(
        (CallbackTask.status == TaskStatus.DOCTOR_REVIEW)
        | (CallbackTask.review_status == ReviewStatus.PENDING_DOCTOR)
    ).count()
    rev_doctor_advised = review_total_query.filter(
        (CallbackTask.review_status == ReviewStatus.DOCTOR_ADVISED)
        | (
            (CallbackTask.status == TaskStatus.DOCTOR_REVIEWED)
            & (CallbackTask.review_status.is_(None))
        )
    ).count()
    rev_pending_followup = review_total_query.filter(
        CallbackTask.review_status == ReviewStatus.PENDING_FOLLOWUP
    ).count()
    rev_closed = review_total_query.filter(
        CallbackTask.review_status == ReviewStatus.CLOSED
    ).count()
    rev_total = review_total_query.count()
    rev_closure_rate = safe_div(rev_closed, rev_total) if rev_total > 0 else 0.0

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
        review_pending_doctor=rev_pending_doctor,
        review_doctor_advised=rev_doctor_advised,
        review_pending_followup=rev_pending_followup,
        review_closed=rev_closed,
        review_closure_rate=rev_closure_rate,
    )
    return overview


@router.get("/by-store", response_model=List[StoreStats])
def get_stats_by_store(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[int] = None,
    treatment_type_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STORE_NURSE))
):
    stores = db.query(Store).all()
    if current_user.role != UserRole.ADMIN and current_user.store_id:
        stores = [s for s in stores if s.id == current_user.store_id]
    elif store_id:
        stores = [s for s in stores if s.id == store_id]

    results = []
    for store in stores:
        query = db.query(CallbackTask).filter(CallbackTask.store_id == store.id)
        query, _, _ = apply_stats_filter(
            query, start_date, end_date, None, None, treatment_type_id
        )

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
    treatment_type_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query_users = db.query(User).filter(User.is_active == True)
    if current_user.role != UserRole.ADMIN and current_user.store_id:
        query_users = query_users.filter(User.store_id == current_user.store_id)
    elif store_id:
        query_users = query_users.filter(or_(User.store_id == store_id, User.store_id.is_(None)))

    users = query_users.filter(User.role.in_([UserRole.CALL_AGENT, UserRole.STORE_NURSE, UserRole.DOCTOR])).all()

    results = []
    for user in users:
        query = db.query(CallbackTask).filter(
            (CallbackTask.assigned_user_id == user.id) |
            (CallbackTask.handled_by_id == user.id)
        )
        query, _, _ = apply_stats_filter(
            query, start_date, end_date, None, None, treatment_type_id
        )

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
            user_name=user.real_name or user.real_name or user.username,
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
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    treatment_type_id: Optional[int] = None,
    limit: int = Query(500, ge=1, le=1000),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CallbackTask).options(
        joinedload(CallbackTask.patient),
        joinedload(CallbackTask.store),
        joinedload(CallbackTask.assigned_user),
        joinedload(CallbackTask.treatment_record).joinedload(TreatmentRecord.treatment_type),
    )

    query = apply_overdue_filter(query)
    query, _, _ = apply_stats_filter(
        query, start_date, end_date, store_id,
        assigned_user_id, treatment_type_id, current_user
    )

    total = query.count()
    timeout_items = query.order_by(
        CallbackTask.due_time.asc()
    ).offset((page - 1) * page_size).limit(page_size).all()

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
            due_time=t.due_time,
            status=t.status.value,
            overdue_hours=overdue_hours,
            treatment_type=t.treatment_record.treatment_type.type_name if (t.treatment_record and t.treatment_record.treatment_type) else None,
            assigned_user=t.assigned_user.real_name if t.assigned_user else None,
        )
        results.append(item)
    return results


@router.get("/abnormal-list", response_model=List[AbnormalTaskItem])
def get_abnormal_tasks_list(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    treatment_type_id: Optional[int] = None,
    only_doctor_review: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CallbackTask).options(
        joinedload(CallbackTask.patient),
        joinedload(CallbackTask.store),
        joinedload(CallbackTask.assigned_user),
        joinedload(CallbackTask.reviewed_by),
        joinedload(CallbackTask.treatment_record).joinedload(TreatmentRecord.treatment_type),
    ).filter(CallbackTask.is_abnormal == True)

    if only_doctor_review:
        query = query.filter(CallbackTask.status.in_([
            TaskStatus.DOCTOR_REVIEW, TaskStatus.DOCTOR_REVIEWED
        ]))

    query, _, _ = apply_stats_filter(
        query, start_date, end_date, store_id,
        assigned_user_id, treatment_type_id, current_user
    )

    total = query.count()
    abnormal_items = query.order_by(
        CallbackTask.created_at.desc()
    ).offset((page - 1) * page_size).limit(page_size).all()

    results = []
    for t in abnormal_items:
        item = AbnormalTaskItem(
            task_id=t.id,
            task_no=t.task_no,
            patient_name=t.patient.name if t.patient else "未知",
            phone=t.patient.phone if t.patient else "",
            store_name=t.store.store_name if t.store else "未知",
            scheduled_date=t.scheduled_date,
            status=t.status.value,
            abnormal_keywords_hit=t.abnormal_keywords_hit,
            treatment_type=t.treatment_record.treatment_type.type_name if (t.treatment_record and t.treatment_record.treatment_type) else None,
            assigned_user=t.assigned_user.real_name if t.assigned_user else None,
            doctor_review_notes=t.doctor_review_notes,
            doctor_conclusion=t.doctor_conclusion,
        )
        results.append(item)
    return results


@router.get("/export/csv")
def export_stats_csv(
    export_type: str = Query("timeout", description="timeout/abnormal/tasks"),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    treatment_type_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STORE_NURSE))
):
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    if export_type == "timeout":
        query = db.query(CallbackTask).options(
            joinedload(CallbackTask.patient),
            joinedload(CallbackTask.store),
            joinedload(CallbackTask.assigned_user),
            joinedload(CallbackTask.treatment_record).joinedload(TreatmentRecord.treatment_type),
        )
        query = apply_overdue_filter(query)
        query, _, _ = apply_stats_filter(
            query, start_date, end_date, store_id,
            assigned_user_id, treatment_type_id, current_user
        )

        writer.writerow([
            "任务编号", "患者姓名", "手机号", "所属门店", "计划回访日期",
            "截止时间", "当前状态", "超时(小时)", "治疗类型", "负责人"
        ])
        now = datetime.utcnow()
        for t in query.order_by(CallbackTask.due_time.asc()).all():
            overdue_hours = round((now - t.due_time).total_seconds() / 3600, 1) if t.due_time else 0
            writer.writerow([
                t.task_no,
                t.patient.name if t.patient else "",
                t.patient.phone if t.patient else "",
                t.store.store_name if t.store else "",
                t.scheduled_date.strftime("%Y-%m-%d"),
                t.due_time.strftime("%Y-%m-%d %H:%M:%S") if t.due_time else "",
                t.status.value,
                overdue_hours,
                t.treatment_record.treatment_type.type_name if (t.treatment_record and t.treatment_record.treatment_type) else "",
                t.assigned_user.real_name if t.assigned_user else "",
            ])
        filename = f"超时任务_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"

    elif export_type == "abnormal":
        query = db.query(CallbackTask).options(
            joinedload(CallbackTask.patient),
            joinedload(CallbackTask.store),
            joinedload(CallbackTask.assigned_user),
            joinedload(CallbackTask.treatment_record).joinedload(TreatmentRecord.treatment_type),
        ).filter(CallbackTask.is_abnormal == True)
        query, _, _ = apply_stats_filter(
            query, start_date, end_date, store_id,
            assigned_user_id, treatment_type_id, current_user
        )

        writer.writerow([
            "任务编号", "患者姓名", "手机号", "所属门店", "计划回访日期",
            "当前状态", "异常关键词", "治疗类型", "负责人",
            "医生复核意见", "处理结论", "建议复诊日期"
        ])
        for t in query.order_by(CallbackTask.created_at.desc()).all():
            writer.writerow([
                t.task_no,
                t.patient.name if t.patient else "",
                t.patient.phone if t.patient else "",
                t.store.store_name if t.store else "",
                t.scheduled_date.strftime("%Y-%m-%d"),
                t.status.value,
                t.abnormal_keywords_hit or "",
                t.treatment_record.treatment_type.type_name if (t.treatment_record and t.treatment_record.treatment_type) else "",
                t.assigned_user.real_name if t.assigned_user else "",
                t.doctor_review_notes or "",
                t.doctor_conclusion or "",
                t.suggested_review_date.strftime("%Y-%m-%d") if t.suggested_review_date else "",
            ])
        filename = f"异常任务_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"

    else:
        query = db.query(CallbackTask).options(
            joinedload(CallbackTask.patient),
            joinedload(CallbackTask.store),
            joinedload(CallbackTask.assigned_user),
            joinedload(CallbackTask.treatment_record).joinedload(TreatmentRecord.treatment_type),
        )
        query, _, _ = apply_stats_filter(
            query, start_date, end_date, store_id,
            assigned_user_id, treatment_type_id, current_user
        )

        writer.writerow([
            "任务编号", "患者姓名", "手机号", "所属门店", "治疗类型",
            "计划回访日期", "拨打时间", "截止时间", "当前状态", "负责人",
            "通话时长(秒)", "异常关键词", "处理备注",
            "医生意见", "处理结论", "建议复诊日期"
        ])
        for t in query.order_by(CallbackTask.created_at.desc()).all():
            writer.writerow([
                t.task_no,
                t.patient.name if t.patient else "",
                t.patient.phone if t.patient else "",
                t.store.store_name if t.store else "",
                t.treatment_record.treatment_type.type_name if (t.treatment_record and t.treatment_record.treatment_type) else "",
                t.scheduled_date.strftime("%Y-%m-%d"),
                t.scheduled_time.strftime("%H:%M:%S") if t.scheduled_time else "",
                t.due_time.strftime("%Y-%m-%d %H:%M:%S") if t.due_time else "",
                t.status.value,
                t.assigned_user.real_name if t.assigned_user else "",
                t.call_duration_seconds or 0,
                t.abnormal_keywords_hit or "",
                t.callback_notes or "",
                t.doctor_review_notes or "",
                t.doctor_conclusion or "",
                t.suggested_review_date.strftime("%Y-%m-%d") if t.suggested_review_date else "",
            ])
        filename = f"全部任务_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"

    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/timeout-count")
def get_timeout_count(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[int] = None,
    assigned_user_id: Optional[int] = None,
    treatment_type_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(CallbackTask)
    query, _, _ = apply_stats_filter(
        query, start_date, end_date, store_id,
        assigned_user_id, treatment_type_id, current_user
    )
    timeout_count = count_overdue_tasks(db, store_id=store_id, base_query=query)
    return {"timeout_count": timeout_count}


@router.get("/rule-effect", response_model=List[RuleEffectItem])
def get_rule_effect_analysis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[int] = None,
    treatment_type_id: Optional[int] = None,
    rule_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STORE_NURSE))
):
    rules_query = db.query(CallbackRule).options(
        joinedload(CallbackRule.treatment_type)
    )
    if treatment_type_id:
        rules_query = rules_query.filter(CallbackRule.treatment_type_id == treatment_type_id)
    if rule_id:
        rules_query = rules_query.filter(CallbackRule.id == rule_id)
    rules = rules_query.all()

    results = []
    for rule in rules:
        query = db.query(CallbackTask).filter(CallbackTask.rule_id == rule.id)
        query, _, _ = apply_stats_filter(
            query, start_date, end_date, store_id, None, None, current_user
        )

        total = query.count()
        if total == 0:
            continue

        abnormal = query.filter(CallbackTask.is_abnormal == True).count()
        timeout = count_overdue_tasks(db, base_query=query)
        doctor_review = query.filter(CallbackTask.status.in_([
            TaskStatus.DOCTOR_REVIEW, TaskStatus.DOCTOR_REVIEWED
        ])).count()

        item = RuleEffectItem(
            treatment_type_id=rule.treatment_type_id,
            treatment_type_name=rule.treatment_type.type_name if rule.treatment_type else "",
            rule_id=rule.id,
            rule_name=rule.rule_name,
            call_window=rule.call_window.value if rule.call_window else None,
            total_tasks=total,
            abnormal_tasks=abnormal,
            abnormal_rate=safe_div(abnormal, total),
            timeout_tasks=timeout,
            timeout_rate=safe_div(timeout, total),
            doctor_review_tasks=doctor_review,
            doctor_review_rate=safe_div(doctor_review, total),
        )
        results.append(item)

    results.sort(key=lambda x: x.abnormal_rate, reverse=True)
    return results


@router.get("/rule-effect/export/csv")
def export_rule_effect_csv(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[int] = None,
    treatment_type_id: Optional[int] = None,
    rule_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STORE_NURSE))
):
    rules_query = db.query(CallbackRule).options(
        joinedload(CallbackRule.treatment_type)
    )
    if treatment_type_id:
        rules_query = rules_query.filter(CallbackRule.treatment_type_id == treatment_type_id)
    if rule_id:
        rules_query = rules_query.filter(CallbackRule.id == rule_id)
    rules = rules_query.all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "治疗类型", "回访规则", "拨打时段", "任务总数",
        "异常数", "异常率(%)", "超时数", "超时率(%)", "转医生数", "转医生比例(%)"
    ])
    for rule in rules:
        query = db.query(CallbackTask).filter(CallbackTask.rule_id == rule.id)
        query, _, _ = apply_stats_filter(
            query, start_date, end_date, store_id, None, None, current_user
        )
        total = query.count()
        if total == 0:
            continue
        abnormal = query.filter(CallbackTask.is_abnormal == True).count()
        timeout = count_overdue_tasks(db, base_query=query)
        doctor_review = query.filter(CallbackTask.status.in_([
            TaskStatus.DOCTOR_REVIEW, TaskStatus.DOCTOR_REVIEWED
        ])).count()
        writer.writerow([
            rule.treatment_type.type_name if rule.treatment_type else "",
            rule.rule_name,
            rule.call_window.value if rule.call_window else "",
            total,
            abnormal, safe_div(abnormal, total),
            timeout, safe_div(timeout, total),
            doctor_review, safe_div(doctor_review, total),
        ])

    buffer.seek(0)
    filename = f"规则效果分析_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
