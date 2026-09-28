from typing import Optional, TypedDict, Literal
from pydantic import BaseModel, Field
from langgraph_finance_agent.llm import light_llm
from langgraph.types import interrupt
from langgraph_finance_agent.account.tools import load_accounts, find_account_number, withdraw

class BillPaymentState(TypedDict):
    user_id: str
    today: str
    request: str
    response: str
    action: Literal["register", "search", "terminate", "unsupported"]

class BillPaymentFormat(BaseModel):
    action: Literal["register", "search", "terminate", "unsupported"] = Field(
        description=(
            "공과금 자동이체 요청의 세부 동작.\n"
            "- register: 새 공과금 자동이체 등록 (예: '전기세 자동이체 등록해줘', "
            "'수도세 매달 15일에 빠지게 해줘')\n"
            "- search: 등록된 자동이체 조회 (예: '내 자동이체 목록 보여줘', '통신비 얼마씩 나가?', '이번 달 공과금 얼마나 나갔어?')\n"
            "- terminate: 등록된 자동이체 해지 (예: '관리비 자동이체 해지해줘')\n"
            "- unsupported: 위 세 가지에 해당하지 않는 요청 (예: 이번 달 청구서 상세 내역 조회, "
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


def unsupported_action(state: BillPaymentFormat):
    return {"response": "지원하지 않는 기능이에요."}


def classify_BillPayment_action(state: BillPaymentFormat):
    # 지연 정산
    # settele_due_bill

    result = light_llm.with_structured_output(BillPaymentFormat).invoke(state["request"])
    return {"action": result.action}


def register_billpayment(state: BillPaymentState):
    accounts = load_accounts(state["user_id"])

    reg_llm = light_llm.with_structured_output(RegisterFormat)
    result = reg_llm.invoke(state["request"])

    if result.bill_type is None:
        return {"response": "등록할 공과금 종류를 말해주세요. (예: '전기', '가스', '수도', '관리비')"}

    if result.customer_number is None:
        return {"response": "공과금 청구기관이 발급한 고객 확인 번호를 입력해주세요."}

    decision = interrupt({
        "question": f"{result.bill_type} "
    })





