from .nodes import create_account,search_account,transfer,terminate_account,rename_account,classify_account_action,unsupported_action
from .nodes import AccountState
from langgraph.graph import START, StateGraph, END

account_builder = StateGraph(AccountState)

account_builder.add_node("create_account", create_account)
account_builder.add_node("search_account", search_account)
account_builder.add_node("transfer", transfer)
account_builder.add_node("terminate_account", terminate_account)
account_builder.add_node("rename_account", rename_account)
account_builder.add_node("classify_account_action", classify_account_action)
account_builder.add_node("unsupported", unsupported_action)

account_builder.add_edge(START, "classify_account_action")
account_builder.add_conditional_edges(
    "classify_account_action",
    lambda state: state["action"],
    {
        "search": "search_account",
        "create": "create_account",
        "transfer": "transfer",
        "terminate": "terminate_account",
        "rename": "rename_account",
        "unsupported": "unsupported"
    }
)

account_builder.add_edge("create_account", END)
account_builder.add_edge("search_account", END)
account_builder.add_edge("transfer", END)
account_builder.add_edge("terminate_account", END)
account_builder.add_edge("rename_account", END)
account_builder.add_edge("unsupported", END)

account_graph = account_builder.compile()