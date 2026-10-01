from typing import Optional, TypedDict, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from langgraph_finance_agent.llm import llm, light_llm
from langgraph.types import Command, interrupt
from langgraph_finance_agent.tools import MAX_SELECT_RETRY
from .tools import load_accounts,save_accounts,generate_account_number,format_accounts,register_account,find_account_number,find_user,execute_transfer, unregister_account

class AccountState(TypedDict):
    user_id: str
    today: str
    request: str
    response: str
    action: Literal["search", "create", "transfer", "terminate", "rename", "unsupported"]

class AccountRouteFormat(BaseModel):
    action: Literal["search", "create", "transfer", "terminate", "rename", "unsupported"] = Field(
        description=(
            "사용자 요청이 계좌 도메인에서 무엇에 해당하는지.\n"
            "- search: 계좌 조회\n"
            "- create: 계좌 개설\n"
            "- transfer: 계좌 간 이체\n"
            "- terminate: 계좌 해지\n"
            "- rename: 계좌 별칭 변경 (예: '계좌 별칭 바꿔줘', '월급통장을 생활비통장으로 바꿔줘')\n"
            "- unsupported: 위 어디에도 해당 안 되면"
        )
    )

class AccountFormat(BaseModel):
    alias: str = Field(description="사용자가 원하는 계좌 별칭 (예: 월급통장, 비상금통장)")

class AccountSearchFormat(BaseModel):
    account_hint: Optional[str] = Field(
        default=None,
        description="사용자가 언급한 계좌번호 또는 별칭. 특정 계좌를 언급하지 않았으면 null (전체 계좌 대상)"
    )
    s_date: Optional[str] = Field(
        default=None,
        description="조회 시작일 (YYYY-MM-DD). 기간 언급이 없으면 null"
    )
    e_date: Optional[str] = Field(
        default=None,
        description="조회 종료일 (YYYY-MM-DD). 기간 언급이 없으면 null"
    )

class TransferFormat(BaseModel):
    from_hint: Optional[str] = Field(default=None, description="출금할 내 계좌(계좌번호 또는 별칭). 계좌가 하나뿐이면 null 가능")
    to_hint: str = Field(description="입금받을 계좌 — 내 계좌면 계좌번호나 별칭, 다른 사람 계좌면 정확한 계좌번호")
    amount: Optional[int] = Field(default=None, description="정확한 이체 금액(원)을 직접 말했을 때만. 언급 없으면 null")
    keep_amount: Optional[int] = Field(
        default=None,
        description="'~원만 남기고 나머지 이체'처럼 출금 계좌에 남길 금액을 말했을 때만(원). "
        "이 경우 실제 이체 금액은 계산해서 채움. amount를 직접 말했으면 null",
    )

class TerminateFormat(BaseModel):
    account_hint: Optional[str] = Field(default=None, description="해지할 내 계좌(계좌번호 또는 별칭). 계좌가 하나뿐이면 null 가능")

class RenameFormat(BaseModel):
    account_hint: Optional[str] = Field(default=None, description="별칭을 바꿀 계좌(계좌번호 또는 기존 별칭). 계좌가 하나뿐이면 null 가능")
    new_alias: Optional[str] = Field(default=None, description="새로 설정할 별칭. 언급 없으면 null")

def unsupported_action(state: AccountState):
    return {"response": "지원하지 않는 기능이에요."}

def classify_account_action(state: AccountState):
    result = light_llm.with_structured_output(AccountRouteFormat).invoke(state["request"])
    return {"action": result.action}

def create_account(state: AccountState):
    accounts = load_accounts(state["user_id"])

    create_account_llm = light_llm.with_structured_output(AccountFormat)
    result = create_account_llm.invoke(state['request'])

    account_number = generate_account_number(accounts)

    register_account(account_number, state["user_id"])
    
    accounts[account_number] = {
        "alias": result.alias,
        "balance": 0,
        "transactions": [],
        "opened_at": state["today"],
    }

    save_accounts(state["user_id"], accounts)

    return {"response": f"'{result.alias}' 계좌가 개설됐어요.\n계좌번호: {account_number}"}


def search_account(state: AccountState):
    accounts = load_accounts(state["user_id"])

    search_llm = light_llm.with_structured_output(AccountSearchFormat)
    result = search_llm.invoke(f"오늘 날짜: {state['today']}\n\n{state['request']}")

    if result.account_hint is None:
        target = accounts

    else:
        target = {
            num: account for num, account in accounts.items()
            if num == result.account_hint
            or result.account_hint in account["alias"] or account["alias"] in result.account_hint
        }

    return {"response": format_accounts(target, result.s_date, result.e_date)}

GUIDE_TRANSFER = (
    "계좌이체를 진행할게요. 다음 정보를 알려주세요.\n"
    "- 출금 계좌 (계좌가 여러 개면 필수, 하나뿐이면 생략 가능)\n"
    "- 받으실 분 계좌번호 (내 계좌면 별칭도 가능, 다른 분 계좌면 정확한 계좌번호)\n"
    "- 이체 금액"
)


def transfer(state: AccountState):
    my_accounts = load_accounts(state["user_id"])
    transfer_llm = light_llm.with_structured_output(TransferFormat)
    result = transfer_llm.invoke(state["request"])

    from_num = find_account_number(my_accounts, result.from_hint)

    if from_num is None:
        return {"response": GUIDE_TRANSFER}

    # 내 계좌로 이체
    to_num = find_account_number(my_accounts, result.to_hint)
    if to_num is not None:
        to_user_id = state["user_id"]

    # 다른 계좌로 이체
    else:
        to_num = result.to_hint
        to_user_id = find_user(to_num)
        if to_user_id is None:
            return {"response": "존재하지 않는 계좌번호예요."}

    if result.amount is not None:
        amount = result.amount
    elif result.keep_amount is not None:
        amount = my_accounts[from_num]["balance"] - result.keep_amount
    else:
        return {"response": GUIDE_TRANSFER}

    if amount <= 0:
        return {"response": "이체 금액이 올바르지 않아요."}

    if my_accounts[from_num]["balance"] < amount:
        return {"response": "잔액이 부족해요."}

    decision = interrupt({
        "question": f"{to_num} 계좌로 {amount:,}원을 이체하시겠어요? (y/n)",
    })

    if decision:
        execute_transfer(state["user_id"], my_accounts, from_num, to_user_id, to_num, amount, state["today"])

        response_lines = [
            f"{amount:,}원 이체 완료했어요.",
            f"[{my_accounts[from_num]['alias']}] {from_num} - 잔액 {my_accounts[from_num]['balance']:,}원",
        ]
        if to_user_id == state["user_id"]:
            response_lines.append(f"[{my_accounts[to_num]['alias']}] {to_num} — 잔액 {my_accounts[to_num]['balance']:,}원")
    
        return {"response": "\n".join(response_lines)}

    return {"response": "계좌이체를 취소했어요."}

GUIDE_TERMINATE_ACCOUNT = "계좌 해지를 진행할게요. 해지할 계좌(계좌번호 또는 별칭)를 알려주세요."


def terminate_account(state: AccountState):
    my_accounts = load_accounts(state["user_id"])
    terminate_llm = light_llm.with_structured_output(TerminateFormat)

    result = terminate_llm.invoke(state["request"])

    target_account = find_account_number(my_accounts, result.account_hint)

    if target_account is None:
        return {"response": GUIDE_TERMINATE_ACCOUNT}

    other_accounts = {num: account for num, account in my_accounts.items() if num != target_account}
        

    if my_accounts[target_account]["balance"]> 0:
        if not other_accounts:
            return {"response": "해지할 계좌에 잔액이 남아있어요. 잔액을 옯길 다른 내 계좌는 없어요. 계좌 잔액을 다른 곳으로 이체하고 다시 시도해주세요."}

        decision = interrupt(
            {
                "question": "해지할 계좌에 잔액이 남아있어요. 다른 내 계좌로 이체하실래요? (y/n)",
            }
        )

        if not decision:
            return {"response": "해지를 취소했어요."}
        
        question = "어느 계좌로 이체하실래요? (취소하려면 '취소'라고 입력)"
        to_account = None
        failed = 0
        while to_account is None:
            to_hint = interrupt(
                {
                    "question": question,
                    "balance": my_accounts[target_account]["balance"],
                    "options": format_accounts(other_accounts, None, None),
                }
            )
            if str(to_hint).strip() == "취소":
                return {"response": "해지를 취소했어요."}
            to_account = find_account_number(other_accounts, to_hint)
            if to_account is None:
                failed += 1
                if failed >= MAX_SELECT_RETRY:
                    return {"response": "이체할 계좌를 찾지 못해 해지를 중단했어요."}
                question = "선택한 계좌를 찾을 수 없어요. 다시 선택해주세요. (취소하려면 '취소'라고 입력)"

        execute_transfer(state["user_id"], my_accounts, target_account, state["user_id"], to_account, my_accounts[target_account]["balance"], state["today"])

    del my_accounts[target_account]
    save_accounts(state["user_id"], my_accounts)

    # 인덱스 파일 삭제
    unregister_account(target_account)

    return {"response": "계좌 해지가 완료됐어요."}


GUIDE_RENAME = "계좌 별칭을 변경할게요. 어느 계좌인지, 새 별칭을 뭘로 할지 알려주세요."


def rename_account(state: AccountState):
    my_accounts = load_accounts(state["user_id"])
    rename_llm = light_llm.with_structured_output(RenameFormat)
    result = rename_llm.invoke(state["request"])

    target_account = find_account_number(my_accounts, result.account_hint)
    if target_account is None:
        return {"response": GUIDE_RENAME}

    if result.new_alias is None:
        return {"response": GUIDE_RENAME}

    old_alias = my_accounts[target_account]["alias"]
    my_accounts[target_account]["alias"] = result.new_alias
    save_accounts(state["user_id"], my_accounts)

    return {"response": f"'{old_alias}' 계좌 별칭을 '{result.new_alias}'(으)로 변경했어요."}







