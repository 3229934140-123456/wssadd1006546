from typing import List, Optional
from datetime import datetime, timedelta, time, date

from ..models.rule import CallTimeWindow


DEFAULT_ABNORMAL_KEYWORDS = "持续出血,发热,发烧,麻木,剧痛,剧烈疼痛,肿胀严重,感染,流脓,晕厥,心慌,胸闷,过敏反应"


def parse_keywords(keywords_str: Optional[str]) -> List[str]:
    if not keywords_str:
        return []
    return [kw.strip() for kw in keywords_str.split(",") if kw.strip()]


def detect_abnormal_keywords(text: str, keywords: List[str]) -> List[str]:
    if not text or not keywords:
        return []
    text_lower = text.lower()
    hits = []
    for kw in keywords:
        if kw.lower() in text_lower:
            hits.append(kw)
    return hits


def get_call_time_window_start_end(window: CallTimeWindow) -> tuple[time, time]:
    if window == CallTimeWindow.MORNING:
        return (time(9, 0), time(12, 0))
    elif window == CallTimeWindow.AFTERNOON:
        return (time(14, 0), time(17, 0))
    elif window == CallTimeWindow.EVENING:
        return (time(18, 0), time(21, 0))
    else:
        return (time(18, 0), time(21, 0))


def calculate_scheduled_time(
    treatment_date: date,
    days_after: int,
    window: CallTimeWindow,
    custom_time: Optional[time] = None
) -> tuple[date, Optional[time]]:
    scheduled_date = treatment_date + timedelta(days=days_after)
    scheduled_time = None
    if custom_time:
        scheduled_time = custom_time
    else:
        start, _ = get_call_time_window_start_end(window)
        scheduled_time = start
    return scheduled_date, scheduled_time


def calculate_due_time(
    scheduled_date: date,
    window: CallTimeWindow,
    custom_time: Optional[time] = None
) -> datetime:
    if custom_time:
        return datetime.combine(scheduled_date, custom_time) + timedelta(hours=2)
    _, end = get_call_time_window_start_end(window)
    return datetime.combine(scheduled_date, end) + timedelta(hours=1)


def generate_task_no(task_count: int) -> str:
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    return f"CB{date_str}{task_count:06d}"
