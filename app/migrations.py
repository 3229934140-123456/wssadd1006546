from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from .database import engine
import logging

logger = logging.getLogger(__name__)

CALLBACK_TASKS_COLUMNS = [
    ("assignment_reason", "VARCHAR(500)"),
    ("assignment_snapshot", "TEXT"),
    ("doctor_review_notes", "TEXT"),
    ("doctor_conclusion", "VARCHAR(50)"),
    ("suggested_review_date", "DATE"),
    ("reviewed_by_id", "INTEGER"),
    ("reviewed_at", "DATETIME"),
    ("review_status", "VARCHAR(50)"),
    ("nurse_followup_notes", "TEXT"),
    ("followup_by_id", "INTEGER"),
    ("followup_at", "DATETIME"),
    ("followup_result", "VARCHAR(100)"),
    ("actual_review_date", "DATE"),
]


def column_exists(engine: Engine, table_name: str, column_name: str) -> bool:
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def run_migrations():
    with engine.connect() as conn:
        inspector = inspect(engine)

        tables = inspector.get_table_names()

        if "callback_tasks" in tables:
            for col_name, col_type in CALLBACK_TASKS_COLUMNS:
                if not column_exists(engine, "callback_tasks", col_name):
                    try:
                        conn.execute(text(
                            f"ALTER TABLE callback_tasks ADD COLUMN {col_name} {col_type}"
                        ))
                        conn.commit()
                        logger.info(f"迁移：callback_tasks 新增字段 {col_name} {col_type}")
                    except Exception as e:
                        logger.warning(f"迁移字段 {col_name} 时出现警告: {e}")
                        conn.rollback()

        if "patient_abnormal_history" not in tables:
            try:
                conn.execute(text("""
                    CREATE TABLE patient_abnormal_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        patient_id INTEGER NOT NULL,
                        task_id INTEGER NOT NULL,
                        store_id INTEGER,
                        abnormal_keywords_hit VARCHAR(500),
                        callback_notes TEXT,
                        doctor_review_notes TEXT,
                        doctor_conclusion VARCHAR(50),
                        suggested_review_date DATE,
                        nurse_followup_notes TEXT,
                        followup_result VARCHAR(100),
                        actual_review_date DATE,
                        closure_reason VARCHAR(200),
                        created_at DATETIME,
                        closed_at DATETIME
                    )
                """))
                conn.execute(text("CREATE INDEX idx_pah_patient_id ON patient_abnormal_history(patient_id)"))
                conn.execute(text("CREATE INDEX idx_pah_task_id ON patient_abnormal_history(task_id)"))
                conn.commit()
                logger.info("迁移：创建 patient_abnormal_history 表")
            except Exception as e:
                logger.warning(f"创建 patient_abnormal_history 表失败: {e}")
                conn.rollback()

        logger.info("数据库迁移完成")
