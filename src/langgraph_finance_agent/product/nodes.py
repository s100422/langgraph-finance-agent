from typing import Optional, TypedDict, Literal
from pydantic import BaseModel, Field
from langgraph_finance_agent.llm import light_llm
from langgraph.types import interrupt
from langgraph_finance_agent.account.tools import load_accounts, find_account_number, withdraw, deposit
from .tools import (
    PRODUCT_CATALOG, LOAN_PRODUCT_NAME, LOAN_RATE, load_products, save_products,
    generate_product_id, find_product_id, format_products, format_catalog,
    resolve_catalog_choice, settle_due_loans, settle_due_installments,
)


class ProductState(TypedDict):
    user_id: str
    today: str
    request: str
    response: str
    action: Literal["subscribe", "search", "terminate", "apply_loan", "unsupported"]


class ProductRouteFormat(BaseModel):
    action: Literal["subscribe", "search", "terminate", "apply_loan", "unsupported"] = Field(
        description=(
            "사용자 요청이 상품 도메인에서 무엇에 해당하는지.\n"
            "- subscribe: 예금/적금 가입 (예: '적금 가입하고 싶어')\n"
            "- search: 가입 상품/대출 조회\n"
            "- terminate: 예금/적금 해지\n"
            "- apply_loan: 대출 신청\n"
            "- unsupported: 위 어디에도 해당 안 되면"
        )
    )


class SubscribeFormat(BaseModel):
    amount: Optional[int] = Field(default=None, description="가입 금액 — 정기예금이면 한 번에 넣을 총액, 정기적금이면 매달 납입할 금액. 언급 없으면 null")
    alias: Optional[str] = Field(default=None, description="상품 별칭. 언급 없으면 null")
    account_hint: Optional[str] = Field(default=None, description="원금을 뺄 내 계좌(계좌번호 또는 별칭). 계좌가 하나뿐이면 null 가능")
    payment_day: Optional[int] = Field(default=None, description="정기적금의 매달 납입일(1~28). 정기예금이거나 언급 없으면 null")


class ProductSearchFormat(BaseModel):
    product_hint: Optional[str] = Field(default=None, description="사용자가 언급한 상품 ID 또는 별칭. 특정 상품을 언급 안 했으면 null")


class TerminateProductFormat(BaseModel):
    product_hint: Optional[str] = Field(default=None, description="해지할 상품(상품 ID 또는 별칭). 상품이 하나뿐이면 null 가능")


class LoanApplyFormat(BaseModel):
    amount: Optional[int] = Field(default=None, description="대출 신청 금액(원). 언급 없으면 null")
    term_months: Optional[int] = Field(default=None, description="대출 기간(개월). 언급 없으면 null")
    alias: Optional[str] = Field(default=None, description="대출 별칭. 언급 없으면 null")
    account_hint: Optional[str] = Field(default=None, description="대출금을 받고 매달 상환할 내 계좌(계좌번호 또는 별칭). 계좌가 하나뿐이면 null 가능")
    payment_day: Optional[int] = Field(default=None, description="매달 상환일(1~28). 언급 없으면 null")


def unsupported_action(state: ProductState):
    return {"response": "지원하지 않는 기능이에요."}


def classify_product_action(state: ProductState):
    settle_due_loans(state["user_id"], state["today"])
    settle_due_installments(state["user_id"], state["today"])

    result = light_llm.with_structured_output(ProductRouteFormat).invoke(state["request"])
    return {"action": result.action}


def subscribe_product(state: ProductState):
    accounts = load_accounts(state["user_id"])

    sub_llm = light_llm.with_structured_output(SubscribeFormat)
    result = sub_llm.invoke(state["request"])

    account_num = find_account_number(accounts, result.account_hint)
    if account_num is None:
        return {"response": "원금을 뺄 계좌를 특정할 수 없어요. 계좌번호나 별칭을 알려주세요."}

    if result.amount is None:
        return {"response": "가입 금액을 알려주세요."}

    if result.amount <= 0:
        return {"response": "가입 금액이 올바르지 않아요."}

    choice = interrupt({
        "question": "가입할 상품을 번호로 선택해주세요.",
        "options": format_catalog(),
    })

    resolved = resolve_catalog_choice(choice)
    if resolved is None:
        return {"response": "선택한 상품을 찾을 수 없어요."}
    product_name, catalog = resolved

    # 정기예금은 목돈을 지금 바로 넣는 거라 잔액이 있어야 함. 정기적금은 매달 납입이라
    # 가입 시점에 전액을 갖고 있을 필요가 없음 (settle_due_installments가 매달 지연 정산)
    if catalog["product_type"] == "savings" and accounts[account_num]["balance"] < result.amount:
        return {"response": "계좌 잔액이 부족해요."}

    decision = interrupt({
        "question": f"'{product_name}'에 가입하시겠어요? (y/n)",
    })

    if not decision:
        return {"response": "가입을 취소했어요."}

    products = load_products(state["user_id"])
    product_id = generate_product_id(products)
    alias = result.alias or product_name

    if catalog["product_type"] == "savings":
        withdraw(state["user_id"], accounts, account_num, result.amount, state["today"])
        products[product_id] = {
            "product_type": "savings",
            "product_name": product_name,
            "alias": alias,
            "linked_account": account_num,
            "status": "active",
            "balance": result.amount,
            "rate": catalog["rate"],
            "term_months": catalog["term_months"],
            "opened_at": state["today"],
        }
        response = f"'{alias}'({product_name}) 가입 완료했어요.\n상품번호: {product_id}"
    else:
        payment_day = result.payment_day or 25
        products[product_id] = {
            "product_type": "installment",
            "product_name": product_name,
            "alias": alias,
            "linked_account": account_num,
            "status": "active",
            "monthly_amount": result.amount,
            "balance": 0,
            "installments_paid": 0,
            "rate": catalog["rate"],
            "term_months": catalog["term_months"],
            "payment_day": payment_day,
            "last_settled_date": state["today"],
            "overdue": False,
            "opened_at": state["today"],
        }
        response = (
            f"'{alias}'({product_name}) 가입 완료했어요.\n상품번호: {product_id}\n"
            f"매달 {payment_day}일에 {result.amount:,}원씩 자동 납입돼요."
        )

    save_products(state["user_id"], products)
    return {"response": response}


def search_product(state: ProductState):
    products = load_products(state["user_id"])

    search_llm = light_llm.with_structured_output(ProductSearchFormat)
    result = search_llm.invoke(state["request"])

    if result.product_hint is None:
        target = products
    else:
        target = {
            pid: product for pid, product in products.items()
            if pid == result.product_hint or product["alias"] == result.product_hint
        }

    return {"response": format_products(target)}


def terminate_product(state: ProductState):
    products = load_products(state["user_id"])

    terminate_llm = light_llm.with_structured_output(TerminateProductFormat)
    result = terminate_llm.invoke(state["request"])

    product_id = find_product_id(products, result.product_hint)
    if product_id is None:
        return {"response": "존재하지 않는 상품이에요."}

    product = products[product_id]

    if product["product_type"] == "loan":
        return {"response": "대출은 해지가 아니라 상환으로 처리돼요 (결제일에 자동으로 상환돼요)."}

    interest = round(product["balance"] * product["rate"])
    payout = product["balance"] + interest

    decision = interrupt({
        "question": f"'{product['alias']}' 해지하고 {payout:,}원(원금+이자 {interest:,}원)을 {product['linked_account']} 계좌로 받으시겠어요? (y/n)",
    })

    if not decision:
        return {"response": "해지를 취소했어요."}

    accounts = load_accounts(state["user_id"])
    deposit(state["user_id"], accounts, product["linked_account"], payout, state["today"])

    product["status"] = "cancelled"
    save_products(state["user_id"], products)

    return {"response": f"'{product['alias']}' 해지 완료, {payout:,}원 입금했어요."}


def apply_loan(state: ProductState):
    accounts = load_accounts(state["user_id"])

    loan_llm = light_llm.with_structured_output(LoanApplyFormat)
    result = loan_llm.invoke(state["request"])

    account_num = find_account_number(accounts, result.account_hint)
    if account_num is None:
        return {"response": "대출금을 받을 계좌를 특정할 수 없어요. 계좌번호나 별칭을 알려주세요."}

    if result.amount is None or result.term_months is None:
        return {"response": "대출 금액과 기간을 알려주세요."}

    if result.amount <= 0 or result.term_months <= 0:
        return {"response": "대출 금액/기간이 올바르지 않아요."}

    payment_day = result.payment_day or 25

    decision = interrupt({
        "question": f"{result.amount:,}원을 {result.term_months}개월 대출로 신청하시겠어요? (y/n)",
    })

    if not decision:
        return {"response": "대출 신청을 취소했어요."}

    deposit(state["user_id"], accounts, account_num, result.amount, state["today"])

    products = load_products(state["user_id"])
    product_id = generate_product_id(products)
    alias = result.alias or LOAN_PRODUCT_NAME
    total_repayable = round(result.amount * (1 + LOAN_RATE))
    monthly_payment = round(total_repayable / result.term_months)

    products[product_id] = {
        "product_type": "loan",
        "product_name": LOAN_PRODUCT_NAME,
        "alias": alias,
        "linked_account": account_num,
        "status": "active",
        "principal": result.amount,
        "rate": LOAN_RATE,
        "term_months": result.term_months,
        "remaining_balance": total_repayable,
        "monthly_payment": monthly_payment,
        "payment_day": payment_day,
        "last_settled_date": state["today"],
        "overdue": False,
        "opened_at": state["today"],
    }
    save_products(state["user_id"], products)

    return {
        "response": (
            f"대출 승인, {result.amount:,}원이 {account_num} 계좌로 입금됐어요.\n"
            f"상품번호: {product_id}\n"
            f"매달 {payment_day}일에 {monthly_payment:,}원씩 자동 상환돼요."
        )
    }
