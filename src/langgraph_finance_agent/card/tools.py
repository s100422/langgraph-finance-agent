import random

from langgraph_finance_agent.account.tools import load_accounts, withdraw
from langgraph_finance_agent.tools import latest_payment_date, load_json, save_json


def load_cards(user_id: str) -> dict:
    return load_json("cards", user_id)


def save_cards(user_id: str, cards: dict) -> None:
    save_json("cards", user_id, cards)


def generate_card_number(existing: dict) -> str:
    while True:
        number = "-".join(f"{random.randint(1000, 9999)}" for _ in range(4))
        if number not in existing:
            return number


def find_card_number(cards: dict, hint: str | None) -> str | None:
    active = {num: card for num, card in cards.items() if card["status"] == "active"}

    if hint is None:
        if len(active) == 1:
            return next(iter(active))
        return None

    for num, card in active.items():
        if num == hint or card["alias"] == hint:
            return num

    return None


def format_cards(cards: dict) -> str:
    if not cards:
        return "조회된 카드가 없어요."

    type_label = {"check": "체크카드", "credit": "신용카드"}
    results = []
    for num, card in cards.items():
        status = "" if card["status"] == "active" else " (해지됨)"
        overdue = " (연체)" if card.get("overdue") else ""
        results.append(
            f"[{card['product_name']}/{card['alias']}] {num} — {type_label[card['card_type']]}{status}{overdue}"
        )
        for usage in card["usages"]:
            results.append(f"  {usage['date']} 사용 {usage['amount']:,}원")

    return "\n".join(results)


def settle_due_credit_cards(user_id: str, today: str) -> None:
    """카드 도메인 요청이 들어올 때마다 호출 — 실시간 스케줄러 없이 결제일 지연 정산."""
    cards = load_cards(user_id)
    accounts = load_accounts(user_id)
    changed = False

    for card in cards.values():
        if card["card_type"] != "credit" or card["status"] != "active":
            continue

        due_date = latest_payment_date(card["payment_day"], today)
        if due_date <= card["last_settled_date"]:
            continue

        pending = sum(
            usage["amount"] for usage in card["usages"]
            if card["last_settled_date"] < usage["date"] <= due_date
        )

        if pending > 0 and accounts[card["linked_account"]]["balance"] < pending:
            card["overdue"] = True
            changed = True
            continue

        if pending > 0:
            withdraw(user_id, accounts, card["linked_account"], pending, today)

        card["last_settled_date"] = due_date
        card["overdue"] = False
        changed = True

    if changed:
        save_cards(user_id, cards)
