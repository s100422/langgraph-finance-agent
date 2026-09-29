import random

from langgraph_finance_agent.account.tools import load_accounts, withdraw
from langgraph_finance_agent.tools import latest_payment_date, load_json, save_json

PRODUCT_CATALOG = {
    "정기예금 12개월": {"product_type": "savings", "term_months": 12, "rate": 0.03},
    "정기예금 24개월": {"product_type": "savings", "term_months": 24, "rate": 0.035},
    "정기적금 12개월": {"product_type": "installment", "term_months": 12, "rate": 0.035},
    "정기적금 24개월": {"product_type": "installment", "term_months": 24, "rate": 0.04},
}

LOAN_PRODUCT_NAME = "신용대출"
LOAN_RATE = 0.05


def load_products(user_id: str) -> dict:
    return load_json("products", user_id)


def save_products(user_id: str, products: dict) -> None:
    save_json("products", user_id, products)


def generate_product_id(existing: dict) -> str:
    while True:
        pid = f"P{random.randint(100000, 999999)}"
        if pid not in existing:
            return pid


def find_product_id(products: dict, hint: str | None) -> str | None:
    active = {pid: product for pid, product in products.items() if product["status"] == "active"}

    if hint is None:
        if len(active) == 1:
            return next(iter(active))
        return None

    for pid, product in active.items():
        if pid == hint or hint in product["alias"] or product["alias"] in hint:
            return pid

    return None


def format_catalog() -> str:
    return "\n".join(
        f"{i}. {name} (금리 연 {info['rate'] * 100:.1f}%)"
        for i, (name, info) in enumerate(PRODUCT_CATALOG.items(), start=1)
    )


def resolve_catalog_choice(choice: str) -> tuple[str, dict] | None:
    names = list(PRODUCT_CATALOG.keys())

    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(names):
            name = names[index]
            return name, PRODUCT_CATALOG[name]
        return None

    if choice in PRODUCT_CATALOG:
        return choice, PRODUCT_CATALOG[choice]

    return None


STATUS_LABEL = {"active": "", "cancelled": " (해지됨)", "paid_off": " (상환완료)", "matured": " (만기)"}


def format_products(products: dict) -> str:
    if not products:
        return "조회된 상품이 없어요."

    results = []
    for pid, p in products.items():
        status = STATUS_LABEL.get(p["status"], "")
        overdue = " (연체)" if p.get("overdue") else ""
        if p["product_type"] == "loan":
            results.append(f"[{p['alias']}] {pid} — {p['product_name']} 대출잔액 {p['remaining_balance']:,}원{status}{overdue}")
        elif p["product_type"] == "installment":
            results.append(
                f"[{p['alias']}] {pid} — {p['product_name']} 누적잔액 {p['balance']:,}원 "
                f"({p['installments_paid']}/{p['term_months']}회 납입){status}{overdue}"
            )
        else:
            results.append(f"[{p['alias']}] {pid} — {p['product_name']} 잔액 {p['balance']:,}원{status}")

    return "\n".join(results)


def settle_due_loans(user_id: str, today: str) -> None:
    products = load_products(user_id)
    accounts = load_accounts(user_id)
    changed = False

    for product in products.values():
        if product["product_type"] != "loan" or product["status"] != "active":
            continue
        if product["remaining_balance"] <= 0:
            continue

        due_date = latest_payment_date(product["payment_day"], today)
        if due_date <= product["last_settled_date"]:
            continue

        payment = min(product["monthly_payment"], product["remaining_balance"])

        if accounts[product["linked_account"]]["balance"] < payment:
            product["overdue"] = True
            changed = True
            continue

        withdraw(user_id, accounts, product["linked_account"], payment, today)
        product["remaining_balance"] -= payment
        product["last_settled_date"] = due_date
        product["overdue"] = False
        if product["remaining_balance"] <= 0:
            product["status"] = "paid_off"
        changed = True

    if changed:
        save_products(user_id, products)


def settle_due_installments(user_id: str, today: str) -> None:
    products = load_products(user_id)
    accounts = load_accounts(user_id)
    changed = False

    for product in products.values():
        if product["product_type"] != "installment" or product["status"] != "active":
            continue
        if product["installments_paid"] >= product["term_months"]:
            continue

        due_date = latest_payment_date(product["payment_day"], today)
        if due_date <= product["last_settled_date"]:
            continue

        if accounts[product["linked_account"]]["balance"] < product["monthly_amount"]:
            product["overdue"] = True
            changed = True
            continue

        withdraw(user_id, accounts, product["linked_account"], product["monthly_amount"], today)
        product["balance"] += product["monthly_amount"]
        product["installments_paid"] += 1
        product["last_settled_date"] = due_date
        product["overdue"] = False
        if product["installments_paid"] >= product["term_months"]:
            product["status"] = "matured"
        changed = True

    if changed:
        save_products(user_id, products)
