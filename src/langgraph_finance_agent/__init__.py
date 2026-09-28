from datetime import datetime
from langgraph.types import Command
from .graph import main_graph


def run_turn(user_id: str, request: str) -> None:
    config = {"configurable": {"thread_id": user_id}}
    result = main_graph.invoke(
        {
            "request": request,
            "user_id": user_id,
            "today": datetime.now().strftime("%Y-%m-%d"),
        },
        config,
    )

    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        print(payload.get("question", ""))
        if "options" in payload:
            print(payload["options"])

        answer = input("> ").strip()
        resume_value = answer == "y" if "(y/n)" in payload.get("question", "") else answer

        result = main_graph.invoke(Command(resume=resume_value), config)

    print(result["response"])


def main() -> None:
    user_id = input("user_id: ").strip()
    while True:
        request = input("\n요청 (quit로 종료): ").strip()
        if request == "quit":
            break
        run_turn(user_id, request)