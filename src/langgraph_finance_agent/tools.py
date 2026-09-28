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
    """오늘 기준으로 가장 최근에 지난(오늘 포함) 결제일을 YYYY-MM-DD로 리턴.

    카드 결제일/대출 상환일처럼 매달 정해진 날짜에 자동 정산되는 걸
    실시간 스케줄러 없이 '도메인 진입 시점에 지연 정산'으로 흉내낼 때 씀.
    """
    # ponytail: 결제일 28일로 캡 — 29~31일 매달 유효성 계산 생략, 필요해지면 calendar.monthrange로 교체
    day = min(payment_day, 28)
    today_date = date.fromisoformat(today)
    candidate = today_date.replace(day=day)

    if candidate > today_date:
        prev_month_last_day = candidate.replace(day=1) - timedelta(days=1)
        candidate = prev_month_last_day.replace(day=day)

    return candidate.isoformat()
