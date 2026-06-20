from typing import List, Optional
from datetime import datetime, date
from sqlalchemy.orm import Session

from ..models import (
    CallbackTask, TaskStatus, TreatmentRecord, CallbackRule,
    Patient, TreatmentType, User, UserRole
)
from .keyword_service import (
    calculate_scheduled_time, calculate_due_time, generate_task_no
)
from .assignment_service import pick_user_for_task


def get_active_rules_for_treatment_type(
    db: Session,
    treatment_type_id: int
) -> List[CallbackRule]:
    return db.query(CallbackRule).filter(
        (CallbackRule.treatment_type_id == treatment_type_id) &
        (CallbackRule.is_active == True)
    ).order_by(CallbackRule.priority.desc(), CallbackRule.days_after_treatment.asc()).all()


def generate_tasks_for_treatment_record(
    db: Session,
    record: TreatmentRecord
) -> List[CallbackTask]:
    patient = db.query(Patient).filter(Patient.id == record.patient_id).first()
    if not patient:
        return []

    rules = get_active_rules_for_treatment_type(db, record.treatment_type_id)
    if not rules:
        return []

    tasks = []
    task_count = db.query(CallbackTask).count()

    for rule in rules:
        scheduled_date, scheduled_time = calculate_scheduled_time(
            treatment_date=record.treatment_date,
            days_after=rule.days_after_treatment,
            window=rule.call_time_window,
            custom_time=rule.custom_call_time
        )
        due_time = calculate_due_time(
            scheduled_date=scheduled_date,
            window=rule.call_time_window,
            custom_time=rule.custom_call_time
        )

        existing = db.query(CallbackTask).filter(
            (CallbackTask.treatment_record_id == record.id) &
            (CallbackTask.rule_id == rule.id)
        ).first()
        if existing:
            continue

        task_count += 1
        task = CallbackTask(
            task_no=generate_task_no(task_count),
            patient_id=record.patient_id,
            store_id=patient.store_id,
            treatment_record_id=record.id,
            rule_id=rule.id,
            scheduled_date=scheduled_date,
            scheduled_time=scheduled_time,
            due_time=due_time,
            status=TaskStatus.PENDING,
            priority=rule.priority,
            is_abnormal=False,
        )
        db.add(task)
        tasks.append(task)

    db.commit()
    for t in tasks:
        db.refresh(t)
    return tasks


def generate_tasks_for_store(
    db: Session,
    store_id: Optional[int] = None
) -> List[CallbackTask]:
    query = db.query(TreatmentRecord)
    if store_id:
        query = query.join(Patient).filter(Patient.store_id == store_id)
    records = query.all()

    all_tasks = []
    for record in records:
        tasks = generate_tasks_for_treatment_record(db, record)
        all_tasks.extend(tasks)
    return all_tasks


def generate_tasks_by_record_ids(
    db: Session,
    record_ids: List[int]
) -> List[CallbackTask]:
    records = db.query(TreatmentRecord).filter(TreatmentRecord.id.in_(record_ids)).all()
    all_tasks = []
    for record in records:
        tasks = generate_tasks_for_treatment_record(db, record)
        all_tasks.extend(tasks)
    return all_tasks


def check_and_mark_timeout_tasks(db: Session) -> int:
    now = datetime.utcnow()
    timeout_tasks = db.query(CallbackTask).filter(
        (CallbackTask.status.in_([TaskStatus.PENDING, TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS])) &
        (CallbackTask.due_time.isnot(None)) &
        (CallbackTask.due_time < now)
    ).all()

    count = 0
    for task in timeout_tasks:
        task.status = TaskStatus.TIMEOUT
        count += 1

    if count > 0:
        db.commit()
    return count


FINISHED_STATUSES = [
    TaskStatus.COMPLETED,
    TaskStatus.DOCTOR_REVIEWED,
    TaskStatus.CANCELLED,
]


def apply_overdue_filter(query, now: Optional[datetime] = None):
    if now is None:
        now = datetime.utcnow()
    return query.filter(
        (CallbackTask.due_time.isnot(None))
        & (CallbackTask.due_time < now)
        & (CallbackTask.status.not_in(FINISHED_STATUSES))
    )


def count_overdue_tasks(db: Session, store_id: Optional[int] = None, base_query=None) -> int:
    if base_query is None:
        base_query = db.query(CallbackTask)
    if store_id:
        base_query = base_query.filter(CallbackTask.store_id == store_id)
    return apply_overdue_filter(base_query).count()

