from typing import Optional, TypedDict, Literal
from pydantic import BaseModel, Field
from langgraph_finance_agent.llm import light_llm
from langgraph.types import interrupt
from langgraph_finance_agent.account.tools import (
    load_accounts, find_account_number, withdraw,
    format_accounts
)
from .tools import (
    generate_bill_payment_id, load_bill_payments, save_bill_payments,
    find_bill_payment_id, format_bill_payments, settle_due_bill_payments,
)


class BillPaymentState(TypedDict):
    user_id: str
    today: str
    request: str
    response: str
    action: Literal["register", "search", "terminate", "rename", "unsupported"]

class BillPaymentFormat(BaseModel):
    action: Literal["register", "search", "terminate", "rename", "unsupported"] = Field(
        description=(
            "공과금 자동이체 요청의 세부 동작.\n"
            "- register: 새 공과금 자동이체 등록 (예: '전기세 자동이체 등록해줘', "
            "'수도세 매달 15일에 빠지게 해줘')\n"
            "- search: 등록된 자동이체 조회 (예: '내 자동이체 목록 보여줘', '통신비 얼마씩 나가?', '이번 달 공과금 얼마나 나갔어?')\n"
            "- terminate: 등록된 자동이체 해지 (예: '관리비 자동이체 해지해줘')\n"
            "- rename: 자동이체 별칭 변경 (예: '자동이체 별칭 바꿔줘', '전기를 본가전기세로 바꿔줘')\n"
            "- unsupported: 위 어디에도 해당하지 않는 요청 (예: 이번 달 청구서 상세 내역 조회, "
            "실시간 요금 조회처럼 이 시스템이 지원하지 않는 기능)"
        )
    )


class RegisterFormat(BaseModel):
    bill_type: Optional[str] = Field(
        default=None,
        description="등록할 공과금 종류 (예: '전기', '가스', '수도', '관리비', '통신비'). "
        "언급 없으면 None",
    )
    alias: Optional[str] = Field(
        default=None,
        description="이 자동이체를 구분할 개인 별칭 (예: '본가 전기세', '자취방 관리비'). "
        "언급 없으면 None — bill_type으로 대체됨",
    )
    customer_number: Optional[str] = Field(
        default=None,
        description="공과금 청구기관이 발급한 고객번호/고객확인번호. 언급 없으면 None",
    )
    payment_day: Optional[int] = Field(
        default=None,
        description="매달 자동으로 출금될 날짜 (1~31 사이 숫자). 언급 없으면 None — "
        "기본값(예: 25일)으로 채워짐",
    )


class BillPaymentSearchFormat(BaseModel):
    bill_hint: Optional[str] = Field(
        default=None,
        description="조회할 특정 공과금의 등록번호 또는 별칭 (예: '전기세', '본가 관리비'). "
        "특정 대상 없이 전체 조회면 None",
    )


class TerminateFormat(BaseModel):
    bill_hint: Optional[str] = Field(
        default=None,
        description="해지할 공과금의 등록번호 또는 별칭 (예: '전기세', '본가 관리비'). "
        "언급 없으면 None",
    )


class RenameBillFormat(BaseModel):
    bill_hint: Optional[str] = Field(
        default=None,
        description="별칭을 바꿀 공과금(등록번호 또는 기존 별칭). 등록된 게 하나뿐이면 None 가능",
    )
    new_alias: Optional[str] = Field(default=None, description="새로 설정할 별칭. 언급 없으면 None")


def unsupported_action(state: BillPaymentState):
    return {"response": "지원하지 않는 기능이에요."}


def classify_bill_payment_action(state: BillPaymentState):
    settle_due_bill_payments(state["user_id"], state["today"])

    result = light_llm.with_structured_output(BillPaymentFormat).invoke(state["request"])
    return {"action": result.action}


GUIDE_REGISTER_BILL = (
    "공과금 자동이체를 등록할게요. 다음 정보를 알려주세요.\n"
    "- 공과금 종류/별칭 (예: '전기', '가스', '수도', '관리비')\n"
    "- 청구기관 고객확인번호\n"
    "- 매달 출금일 (안 말하면 기본값 25일로 채워져요)"
)


def register_bill_payment(state: BillPaymentState):
    accounts = load_accounts(state["user_id"])

    reg_llm = light_llm.with_structured_output(RegisterFormat)
    result = reg_llm.invoke(state["request"])

    if result.bill_type is None:
        return {"response": GUIDE_REGISTER_BILL}

    if result.customer_number is None:
        return {"response": GUIDE_REGISTER_BILL}

    question = f"""
'{result.bill_type}'에 연결할 계좌번호를 입력하세요.
{format_accounts(accounts, None, None)}
"""
    account_num = None
    while account_num is None:
        decision = interrupt({"question": question})
        account_num = find_account_number(accounts, decision)
        if account_num is None:
            question = f"계좌를 찾을 수 없어요. 다시 입력해주세요.\n{format_accounts(accounts, None, None)}"

    bill_payment = load_bill_payments(state["user_id"])
    bill_payment_id = generate_bill_payment_id(bill_payment)
    alias = result.alias or result.bill_type
    payment_day = result.payment_day or 25

    bill_payment[bill_payment_id] = {
        "bill_type": result.bill_type,
        "alias": alias,
        "customer_number": result.customer_number,
        "linked_account": account_num,
        "amount": 0,
        "payment_day": payment_day,
        "last_settled_date": state["today"],
        "status": "active",
        "overdue": False,
    }
    response = (
        f"'{alias}'({result.bill_type}) 등록 완료했어요.\n등록번호: {bill_payment_id}\n"
        f"매달 {payment_day}일에 자동 납입돼요."
    )

    save_bill_payments(state["user_id"], bill_payment)

    return {"response": response}


def search_bill_payment(state: BillPaymentState):
    bill_payments = load_bill_payments(state["user_id"])

    search_llm = light_llm.with_structured_output(BillPaymentSearchFormat)
    result = search_llm.invoke(state["request"])

    if result.bill_hint is None:
        target = bill_payments
    else:
        target = {
            bid: bp for bid, bp in bill_payments.items()
            if bid == result.bill_hint
            or result.bill_hint in bp["alias"] or bp["alias"] in result.bill_hint
        }

    return {"response": format_bill_payments(target)}


GUIDE_TERMINATE_BILL = "공과금 자동이체 해지를 진행할게요. 해지할 자동이체(등록번호 또는 별칭)를 알려주세요."


def terminate_bill_payment(state: BillPaymentState):
    bill_payments = load_bill_payments(state["user_id"])

    terminate_llm = light_llm.with_structured_output(TerminateFormat)
    result = terminate_llm.invoke(state["request"])

    bill_payment_id = find_bill_payment_id(bill_payments, result.bill_hint)
    if bill_payment_id is None:
        return {"response": GUIDE_TERMINATE_BILL}

    bp = bill_payments[bill_payment_id]

    decision = interrupt({
        "question": f"'{bp['alias']}'({bp['bill_type']}) 자동이체를 해지하시겠어요? (y/n)",
    })

    if not decision:
        return {"response": "해지를 취소했어요."}

    bp["status"] = "cancelled"
    save_bill_payments(state["user_id"], bill_payments)

    return {"response": f"'{bp['alias']}' 자동이체가 해지됐어요."}


GUIDE_RENAME_BILL = "자동이체 별칭을 변경할게요. 어느 자동이체인지, 새 별칭을 뭘로 할지 알려주세요."


def rename_bill_payment(state: BillPaymentState):
    bill_payments = load_bill_payments(state["user_id"])

    rename_llm = light_llm.with_structured_output(RenameBillFormat)
    result = rename_llm.invoke(state["request"])

    bill_payment_id = find_bill_payment_id(bill_payments, result.bill_hint)
    if bill_payment_id is None:
        return {"response": GUIDE_RENAME_BILL}

    if result.new_alias is None:
        return {"response": GUIDE_RENAME_BILL}

    old_alias = bill_payments[bill_payment_id]["alias"]
    bill_payments[bill_payment_id]["alias"] = result.new_alias
    save_bill_payments(state["user_id"], bill_payments)

    return {"response": f"'{old_alias}' 자동이체 별칭을 '{result.new_alias}'(으)로 변경했어요."}






