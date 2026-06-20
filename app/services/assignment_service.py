from typing import List, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import or_
import json

from ..models import User, UserRole, CallbackTask, TaskStatus, Patient, RiskLevel
from ..models.task import CallbackTask
from .keyword_service import generate_task_no, parse_keywords


def has_special_risk_tags(patient: Patient) -> bool:
    if not patient.risk_tags:
        return False
    tags = parse_keywords(patient.risk_tags)
    special_keywords = ["高血压", "糖尿病", "心脏病", "过敏", "孕妇", "长期服药"]
    for tag in tags:
        for kw in special_keywords:
            if kw in tag:
                return True
    return False


def find_assignable_users(db: Session, store_id: Optional[int] = None) -> List[User]:
    query = db.query(User).filter(User.is_active == True)
    if store_id:
        query = query.filter(
            or_(
                (User.role == UserRole.STORE_NURSE) & (User.store_id == store_id),
                (User.role == UserRole.CALL_AGENT) & (User.store_id.is_(None)),
                (User.role == UserRole.CALL_AGENT) & (User.store_id == store_id),
            )
        )
    else:
        query = query.filter(User.role.in_([UserRole.CALL_AGENT, UserRole.STORE_NURSE]))
    return query.all()


def find_doctor_users(db: Session, store_id: Optional[int] = None) -> List[User]:
    query = db.query(User).filter(
        (User.is_active == True) &
        (User.role == UserRole.DOCTOR)
    )
    if store_id:
        query = query.filter(User.store_id == store_id)
    return query.all()


def calculate_user_load_score(db: Session, user_id: int) -> tuple[int, int]:
    pending = db.query(CallbackTask).filter(
        (CallbackTask.assigned_user_id == user_id) &
        (CallbackTask.status.in_([TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS]))
    ).count()
    done_today = db.query(CallbackTask).filter(
        (CallbackTask.handled_by_id == user_id) &
        (CallbackTask.status.in_([TaskStatus.COMPLETED, TaskStatus.ABNORMAL, TaskStatus.DOCTOR_REVIEW]))
    ).count()
    return pending, done_today


def pick_user_for_task(
    db: Session,
    patient: Patient,
    store_id: int,
    risk_level: RiskLevel
) -> tuple[Optional[User], dict]:
    users = find_assignable_users(db, store_id)
    if not users:
        users = find_assignable_users(db, None)
    if not users:
        return None, {}

    has_special = has_special_risk_tags(patient)

    candidates = []
    candidate_scores = []
    for u in users:
        pending, done = calculate_user_load_score(db, u.id)
        score = pending * 10 - done

        is_call_agent = u.role == UserRole.CALL_AGENT
        is_store_nurse_same_store = (
            u.role == UserRole.STORE_NURSE and u.store_id == store_id
        )
        is_hq_call_agent = is_call_agent and u.store_id is None
        is_store_call_agent = is_call_agent and u.store_id == store_id

        adjustment = 0
        role_label = ""

        if risk_level == RiskLevel.LOW and not has_special:
            if is_hq_call_agent:
                score -= 15
                adjustment = -15
                role_label = "总部坐席"
            elif is_store_call_agent:
                score -= 10
                adjustment = -10
                role_label = "本店坐席"
            elif is_store_nurse_same_store:
                score -= 3
                adjustment = -3
                role_label = "本店护士"
        elif risk_level == RiskLevel.MEDIUM and not has_special:
            if is_store_nurse_same_store:
                score -= 10
                adjustment = -10
                role_label = "本店护士"
            elif is_store_call_agent:
                score -= 8
                adjustment = -8
                role_label = "本店坐席"
            elif is_hq_call_agent:
                score -= 5
                adjustment = -5
                role_label = "总部坐席"
        elif risk_level == RiskLevel.HIGH or has_special:
            if is_store_nurse_same_store:
                score -= 20
                adjustment = -20
                role_label = "本店护士"
            elif is_store_call_agent:
                score -= 5
                adjustment = -5
                role_label = "本店坐席"
            elif is_hq_call_agent:
                score -= 0
                adjustment = 0
                role_label = "总部坐席"

        candidates.append((score, u))
        candidate_scores.append({
            "user_id": u.id,
            "user_name": u.real_name or u.username,
            "user_role": u.role.value,
            "role_label": role_label,
            "pending": pending,
            "done_today": done,
            "base_score": pending * 10 - done,
            "risk_adjustment": adjustment,
            "final_score": score
        })

    candidates.sort(key=lambda x: x[0])
    selected_user = candidates[0][1] if candidates else None

    reason_parts = []
    if has_special:
        reason_parts.append(f"含特殊标签[{patient.risk_tags}]")
    reason_parts.append(f"风险等级[{risk_level.value}]")
    if selected_user:
        if selected_user.role == UserRole.CALL_AGENT and selected_user.store_id is None:
            reason_parts.append("低风险优先分配总部客服")
        elif selected_user.role == UserRole.STORE_NURSE:
            reason_parts.append("高风险优先分配门店护士")
        else:
            reason_parts.append("按门店匹配分配")
    reason_parts.append(f"候选{len(candidates)}人，综合评分最优")
    reason_summary = "，".join(reason_parts)

    detail = {
        "patient_risk_level": risk_level.value,
        "patient_risk_tags": patient.risk_tags,
        "has_special_tags": has_special,
        "candidate_scores": candidate_scores,
        "final_decision": f"用户ID {selected_user.id} ({selected_user.real_name or selected_user.username})" if selected_user else "无合适人选",
        "reason_summary": reason_summary
    }

    return selected_user, detail


def pick_doctor_for_task(db: Session, store_id: int) -> Optional[User]:
    doctors = find_doctor_users(db, store_id)
    if not doctors:
        doctors = find_doctor_users(db, None)
    if not doctors:
        return None
    return doctors[0]


def assign_task_to_user(
    db: Session,
    task: CallbackTask,
    user_id: int,
    reassigned_reason: Optional[str] = None
) -> CallbackTask:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("用户不存在")
    if task.assigned_user_id and task.status in [TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS]:
        task.reassigned_from_id = task.assigned_user_id
        task.reassigned_at = datetime.utcnow()
        task.reassigned_reason = reassigned_reason or "转派"
    task.assigned_user_id = user_id
    task.assigned_at = datetime.utcnow()
    task.status = TaskStatus.ASSIGNED
    db.commit()
    db.refresh(task)
    return task


def auto_assign_pending_tasks(db: Session, limit: int = 50):
    pending_tasks = db.query(CallbackTask).filter(
        (CallbackTask.status == TaskStatus.PENDING) &
        (CallbackTask.assigned_user_id.is_(None))
    ).order_by(
        CallbackTask.priority.desc(),
        CallbackTask.scheduled_date.asc(),
        CallbackTask.created_at.asc()
    ).limit(limit).all()

    assigned_count = 0
    for task in pending_tasks:
        patient = task.patient
        if not patient:
            continue
        user, detail = pick_user_for_task(
            db,
            patient=patient,
            store_id=task.store_id,
            risk_level=patient.risk_level
        )
        if user:
            task.assigned_user_id = user.id
            task.assigned_at = datetime.utcnow()
            task.status = TaskStatus.ASSIGNED
            task.assignment_reason = detail.get("reason_summary", "")
            detail["assigned_at"] = datetime.utcnow().isoformat()
            detail["assignment_type"] = "auto"
            try:
                task.assignment_snapshot = json.dumps(detail, ensure_ascii=False)
            except:
                pass
            assigned_count += 1

    db.commit()
    return assigned_count


def get_assignment_reason_detail(
    db: Session,
    task: CallbackTask
) -> Tuple[dict, bool]:
    if task.assignment_snapshot:
        try:
            snapshot = json.loads(task.assignment_snapshot)
            return snapshot, True
        except:
            pass

    patient = task.patient
    if not patient:
        return {"error": "患者信息缺失"}, False

    _, detail = pick_user_for_task(
        db,
        patient=patient,
        store_id=task.store_id,
        risk_level=patient.risk_level
    )
    return detail, False
