from typing import Optional, TypedDict, Literal
from pydantic import BaseModel, Field
from langgraph_finance_agent.llm import light_llm
from langgraph.types import interrupt
from langgraph_finance_agent.account.tools import load_accounts, find_account_number, withdraw
from .tools import (
    load_cards, save_cards, generate_card_number, find_card_number,
    format_cards, settle_due_credit_cards,
)


class CardState(TypedDict):
    user_id: str
    today: str
    request: str
    response: str
    action: Literal["create", "search", "use", "cancel", "rename", "unsupported"]


class CardRouteFormat(BaseModel):
    action: Literal["create", "search", "use", "cancel", "rename", "unsupported"] = Field(
        description=(
            "사용자 요청이 카드 도메인에서 무엇에 해당하는지.\n"
            "- create: 카드 발급 (예: '체크카드 만들어줘', '신용카드 발급해줘')\n"
            "- search: 카드 목록/사용내역 조회\n"
            "- use: 카드 결제/사용 기록 (예: '카드로 3만원 결제했어')\n"
            "- cancel: 카드 해지\n"
            "- rename: 카드 별칭 변경 (예: '카드 별칭 바꿔줘', '데일리카드를 쇼핑카드로 바꿔줘')\n"
            "- unsupported: 위 어디에도 해당 안 되면"
        )
    )


class CardCreateFormat(BaseModel):
    card_type: Literal["check", "credit"] = Field(description="체크카드인지 신용카드인지")
    product_name: Optional[str] = Field(default=None, description="카드 상품명 (예: 나라사랑카드). 언급 없으면 null")
    alias: Optional[str] = Field(default=None, description="사용자가 부르고 싶은 카드 별칭. 언급 없으면 null")
    account_hint: Optional[str] = Field(default=None, description="연결할 내 계좌(계좌번호 또는 별칭). 계좌가 하나뿐이면 null 가능")
    payment_day: Optional[int] = Field(default=None, description="신용카드 결제일(1~28). 체크카드거나 언급 없으면 null")


class CardSearchFormat(BaseModel):
    card_hint: Optional[str] = Field(default=None, description="사용자가 언급한 카드번호 또는 별칭. 특정 카드를 언급 안 했으면 null")


class CardUseFormat(BaseModel):
    card_hint: Optional[str] = Field(default=None, description="사용한 카드(카드번호 또는 별칭). 카드가 하나뿐이면 null 가능")
    amount: Optional[int] = Field(default=None, description="결제 금액(원). 언급 없으면 null")


class CardCancelFormat(BaseModel):
    card_hint: Optional[str] = Field(default=None, description="해지할 카드(카드번호 또는 별칭). 카드가 하나뿐이면 null 가능")


class CardRenameFormat(BaseModel):
    card_hint: Optional[str] = Field(default=None, description="별칭을 바꿀 카드(카드번호 또는 기존 별칭). 카드가 하나뿐이면 null 가능")
    new_alias: Optional[str] = Field(default=None, description="새로 설정할 별칭. 언급 없으면 null")


def unsupported_action(state: CardState):
    return {"response": "지원하지 않는 기능이에요."}


def classify_card_action(state: CardState):
    settle_due_credit_cards(state["user_id"], state["today"])

    result = light_llm.with_structured_output(CardRouteFormat).invoke(state["request"])
    return {"action": result.action}


GUIDE_CREATE_CARD = (
    "카드 발급을 진행할게요. 다음 정보를 알려주세요.\n"
    "- 체크카드/신용카드 여부\n"
    "- 연결할 계좌\n"
    "- 카드 상품명/별칭 (선택)\n"
    "- 신용카드면 매달 결제일 (안 말하면 기본값 25일)"
)


def create_card(state: CardState):
    accounts = load_accounts(state["user_id"])

    create_llm = light_llm.with_structured_output(CardCreateFormat)
    result = create_llm.invoke(state["request"])

    account_num = find_account_number(accounts, result.account_hint)
    if account_num is None:
        return {"response": GUIDE_CREATE_CARD}

    cards = load_cards(state["user_id"])
    card_number = generate_card_number(cards)

    product_name = result.product_name or ("일반체크카드" if result.card_type == "check" else "일반신용카드")
    alias = result.alias or product_name

    card = {
        "card_type": result.card_type,
        "product_name": product_name,
        "alias": alias,
        "linked_account": account_num,
        "status": "active",
        "issued_at": state["today"],
        "usages": [],
    }

    if result.card_type == "credit":
        card["payment_day"] = result.payment_day or 25
        card["last_settled_date"] = state["today"]
        card["overdue"] = False

    cards[card_number] = card
    save_cards(state["user_id"], cards)

    type_label = "체크카드" if result.card_type == "check" else "신용카드"
    return {"response": f"'{product_name}'({alias}) {type_label}가 발급됐어요.\n카드번호: {card_number}"}


def search_card(state: CardState):
    cards = load_cards(state["user_id"])

    search_llm = light_llm.with_structured_output(CardSearchFormat)
    result = search_llm.invoke(state["request"])

    if result.card_hint is None:
        target = cards
    else:
        target = {
            num: card for num, card in cards.items()
            if num == result.card_hint
            or result.card_hint in card["alias"] or card["alias"] in result.card_hint
        }

    return {"response": format_cards(target)}


GUIDE_USE_CARD = (
    "카드 결제 기록을 남길게요. 다음 정보를 알려주세요.\n"
    "- 사용한 카드 (카드가 여러 개면 필수)\n"
    "- 결제 금액"
)


def use_card(state: CardState):
    cards = load_cards(state["user_id"])

    use_llm = light_llm.with_structured_output(CardUseFormat)
    result = use_llm.invoke(state["request"])

    card_num = find_card_number(cards, result.card_hint)
    if card_num is None:
        return {"response": GUIDE_USE_CARD}

    if result.amount is None:
        return {"response": GUIDE_USE_CARD}

    if result.amount <= 0:
        return {"response": "결제 금액이 올바르지 않아요."}

    card = cards[card_num]

    if card["card_type"] == "check":
        accounts = load_accounts(state["user_id"])
        if accounts[card["linked_account"]]["balance"] < result.amount:
            return {"response": "연결계좌 잔액이 부족해요."}
        withdraw(state["user_id"], accounts, card["linked_account"], result.amount, state["today"])

    card["usages"].append({"date": state["today"], "amount": result.amount})
    save_cards(state["user_id"], cards)

    return {"response": f"{result.amount:,}원 결제 기록했어요."}


GUIDE_CANCEL_CARD = "카드 해지를 진행할게요. 해지할 카드(카드번호 또는 별칭)를 알려주세요."


def cancel_card(state: CardState):
    cards = load_cards(state["user_id"])

    cancel_llm = light_llm.with_structured_output(CardCancelFormat)
    result = cancel_llm.invoke(state["request"])

    card_num = find_card_number(cards, result.card_hint)
    if card_num is None:
        return {"response": GUIDE_CANCEL_CARD}

    decision = interrupt({
        "question": f"[{cards[card_num]['alias']}] {card_num} 카드를 해지하시겠어요? (y/n)",
    })

    if not decision:
        return {"response": "카드 해지를 취소했어요."}

    cards[card_num]["status"] = "cancelled"
    save_cards(state["user_id"], cards)

    return {"response": "카드가 해지됐어요."}


GUIDE_RENAME_CARD = "카드 별칭을 변경할게요. 어느 카드인지, 새 별칭을 뭘로 할지 알려주세요."


def rename_card(state: CardState):
    cards = load_cards(state["user_id"])

    rename_llm = light_llm.with_structured_output(CardRenameFormat)
    result = rename_llm.invoke(state["request"])

    card_num = find_card_number(cards, result.card_hint)
    if card_num is None:
        return {"response": GUIDE_RENAME_CARD}

    if result.new_alias is None:
        return {"response": GUIDE_RENAME_CARD}

    old_alias = cards[card_num]["alias"]
    cards[card_num]["alias"] = result.new_alias
    save_cards(state["user_id"], cards)

    return {"response": f"'{old_alias}' 카드 별칭을 '{result.new_alias}'(으)로 변경했어요."}
