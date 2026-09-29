import json
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path("data")


def load_json(prefix: str, user_id: str) -> dict:
    path = DATA_DIR / f"{prefix}_{user_id}.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(prefix: str, user_id: str, data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / f"{prefix}_{user_id}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def latest_payment_date(payment_day: int, today: str) -> str:
    day = min(payment_day, 28)
    today_date = date.fromisoformat(today)
    candidate = today_date.replace(day=day)

    if candidate > today_date:
        prev_month_last_day = candidate.replace(day=1) - timedelta(days=1)
        candidate = prev_month_last_day.replace(day=day)

    return candidate.isoformat()
