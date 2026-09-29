from typing import Optional, TypedDict, Literal
from pydantic import BaseModel, Field
from langgraph_finance_agent.llm import light_llm
from langgraph_finance_agent.account.graph import account_graph
from langgraph_finance_agent.card.graph import card_graph
from langgraph_finance_agent.product.graph import product_graph
from langgraph_finance_agent.bill_payment.graph import bill_payment_graph
from langchain_core.runnables import RunnableConfig


class MainState(TypedDict):
    user_id: str
    today: str
    request: str
    category: Literal["account", "bill_payment", "card", "product", "unsupported"]
    response: str


class CategoryRouteFormat(BaseModel):
    category: Literal["account", "bill_payment", "card", "product", "unsupported"] = Field(
        description=(
            "사용자 요청이 속하는 도메인 하나를 고르세요.\n"
            "- account: 입출금 계좌 개설/조회/해지, 계좌 간 이체 (예: '계좌 만들어줘', '잔액 조회해줘', "
            "'다른 계좌로 이체해줘', '계좌 해지해줘')\n"
            "- product: 예적금 가입/해지, 대출 신청/조회 (예: '적금 가입하고 싶어', '대출 신청해줘')\n"
            "- card: 카드 발급/조회/사용/해지\n"
            "- bill_payment: 공과금(전기세, 수도세, 가스비, 관리비 등) 자동이체 등록/조회/해지 "
            "(예: '전기세 자동이체 등록해줘', '자동이체 등록한 것 보여줘', '자동이체 목록 조회', '관리비 자동이체 해지해줘'). "
            "'자동이체'라는 단어가 들어가면 계좌 이체가 아니라 이 카테고리\n"
            "- unsupported: 위 어디에도 해당 안 되는 요청"
        )
    )


def classify_category(state: MainState):
    result = light_llm.with_structured_output(CategoryRouteFormat).invoke(state["request"])
    return {"category": result.category}


def unsupported_category(state: MainState):
    return {"response": "지원하지 않는 기능이에요."}


def account_wrapper(state: MainState, config: RunnableConfig):
    result = account_graph.invoke(
        {
        "user_id": state["user_id"],
        "today": state["today"],
        "request": state["request"],
        },
        config
    )
    return {"response": result["response"]}


def product_wrapper(state: MainState, config: RunnableConfig):
    result = product_graph.invoke(
        {
        "user_id": state["user_id"],
        "today": state["today"],
        "request": state["request"],
        },
        config
    )
    return {"response": result["response"]}


def bill_payment_wrapper(state: MainState, config: RunnableConfig):
    result = bill_payment_graph.invoke(
        {
        "user_id": state["user_id"],
        "today": state["today"],
        "request": state["request"],
        },
        config
    )
    return {"response": result["response"]}


def card_wrapper(state: MainState, config: RunnableConfig):
    result = card_graph.invoke(
        {
        "user_id": state["user_id"],
        "today": state["today"],
        "request": state["request"],
        },
        config
    )
    return {"response": result["response"]}