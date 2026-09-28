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
            "- account: 입출금 계좌 개설/조회/이체/해지 (예: '계좌 만들어줘', '잔액 조회해줘', '이체해줘', '계좌 해지해줘')\n"
            "- product: 예적금 가입/해지, 대출 신청/조회 (예: '적금 가입하고 싶어', '대출 신청해줘')\n"
            "- card: 카드 발급/조회/사용/해지\n"
            "- bill_payment: 공과금(전기세, 수도세 등) 조회/납부\n"
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