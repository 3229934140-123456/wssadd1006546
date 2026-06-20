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

        logger.info("数据库迁移完成")
