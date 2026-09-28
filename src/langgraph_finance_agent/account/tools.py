import json
import random

from langgraph_finance_agent.tools import DATA_DIR, load_json, save_json

INDEX_FILE = DATA_DIR / "account_index.json"

def load_index() -> dict:
    if not INDEX_FILE.exists():
        return {}
    with open(INDEX_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def register_account(account_number: str, user_id: str) -> None:
    index = load_index()
    index[account_number] = user_id
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

def find_user(account_number: str) -> str | None:
    return load_index().get(account_number)

def load_accounts(user_id: str) -> dict:
    return load_json("accounts", user_id)

def save_accounts(user_id: str, accounts: dict) -> None:
    save_json("accounts", user_id, accounts)


def generate_account_number(existing: dict) -> str:
    while True:
        number = f"110-{random.randint(10,99)}-{random.randint(100,999)}"
        if number not in existing:
            return number


def format_accounts(accounts: dict, s_date: str | None, e_date: str | None) -> str:
    if not accounts:
        return "조회된 계좌가 없어요."

    results = []
    for num, account in accounts.items():
        results.append(f"[{account['alias']}] {num} — 잔액 {account['balance']:,}원")

        txs = account["transactions"]
        if s_date or e_date:
            txs = [
                t for t in txs
                if (s_date is None or t["date"] >= s_date)
                and (e_date is None or t["date"] <= e_date)
            ]
        for t in txs:
            results.append(f"  {t['date']} {t['type']} {t['amount']:,}원")

    return "\n".join(results)

def find_account_number(accounts: dict, hint: str | None) -> str | None:
    if hint is None:
        if len(accounts) == 1:
            return next(iter(accounts))
        return None

    for num, account in accounts.items():
        if num == hint or account["alias"] == hint:
            return num

    return None

def execute_transfer(
        my_user_id: str, my_accounts: dict, from_num: str,
        to_user_id: str, to_num: str, amount: int, today: str,
) -> None:
    target_accounts = my_accounts if to_user_id == my_user_id else load_accounts(to_user_id)

    my_accounts[from_num]["balance"] -= amount
    my_accounts[from_num]["transactions"].append(
        {"date": today, "type": "출금", "amount": amount}
    )
    target_accounts[to_num]["balance"] += amount
    target_accounts[to_num]["transactions"].append(
        {"date": today, "type": "입금", "amount": amount}
    )

    save_accounts(my_user_id, my_accounts)
    if to_user_id != my_user_id:
        save_accounts(to_user_id, target_accounts)

def unregister_account(account_number: str) -> None:
    index = load_index()
    index.pop(account_number, None)
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def withdraw(user_id: str, accounts: dict, account_num: str, amount: int, today: str) -> None:
    """카드 결제/대출 상환처럼 상대 계좌 없이 내 계좌에서만 돈이 빠져나가는 경우 공용으로 씀."""
    accounts[account_num]["balance"] -= amount
    accounts[account_num]["transactions"].append({"date": today, "type": "출금", "amount": amount})
    save_accounts(user_id, accounts)


def deposit(user_id: str, accounts: dict, account_num: str, amount: int, today: str) -> None:
    """대출 실행/예적금 해지 환급처럼 상대 계좌 없이 내 계좌로만 돈이 들어오는 경우 공용으로 씀."""
    accounts[account_num]["balance"] += amount
    accounts[account_num]["transactions"].append({"date": today, "type": "입금", "amount": amount})
    save_accounts(user_id, accounts)