import random

from langgraph_finance_agent.account.tools import load_accounts, withdraw
from langgraph_finance_agent.tools import latest_payment_date, load_json, save_json


def generate_bill_payment_id(existing: dict) -> str:
    while True:
        bid = f"B{random.randint(100000, 999999)}"
        if bid not in existing:
            return bid


def load_bill_payments(user_id: str) -> dict:
    return load_json("bill_payment", user_id)


def save_bill_payments(user_id: str, bill_payment: dict) -> None:
    save_json("bill_payment", user_id, bill_payment)


def find_bill_payment_id(bill_payments: dict, hint: str | None) -> str | None:
    active = {bid: bill_payment for bid, bill_payment in bill_payments.items() if bill_payment["status"] == "active"}

    if hint is None:
        if len(active) == 1:
            return next(iter(active))
        return None

    for bid, bill_payment in active.items():
        if bid == hint or hint in bill_payment["alias"] or bill_payment["alias"] in hint:
            return bid

    return None


def format_bill_payments(bill_payments: dict) -> str:
    if not bill_payments:
        return "등록된 공과금 자동이체가 없어요."

    results = []
    for bid, bill_payment in bill_payments.items():
        status = "" if bill_payment["status"] == "active" else " (해지됨)"
        overdue = " (연체)" if bill_payment.get("overdue") else ""
        results.append(
            f"[{bill_payment['alias']}] {bid} — {bill_payment['bill_type']} 최근 청구액 {bill_payment['amount']:,}원 "
            f"(매달 {bill_payment['payment_day']}일 출금){status}{overdue}"
        )

    return "\n".join(results)


def settle_due_bill_payments(user_id: str, today: str) -> None:
    bill_payments = load_bill_payments(user_id)
    accounts = load_accounts(user_id)
    changed = False

    for bill_payment in bill_payments.values():
        if bill_payment["status"] != "active":
            continue

        due_date = latest_payment_date(bill_payment["payment_day"], today)
        if due_date <= bill_payment["last_settled_date"]:
            continue

        amount = random.randint(20000, 80000)

        if accounts[bill_payment["linked_account"]]["balance"] < amount:
            bill_payment["overdue"] = True
            changed = True
            continue

        withdraw(user_id, accounts, bill_payment["linked_account"], amount, today)
        bill_payment["amount"] = amount
        bill_payment["last_settled_date"] = due_date
        bill_payment["overdue"] = False
        changed = True

    if changed:
        save_bill_payments(user_id, bill_payments)