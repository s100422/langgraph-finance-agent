from .nodes import create_card, search_card, use_card, cancel_card, rename_card, classify_card_action, unsupported_action
from .nodes import CardState
from langgraph.graph import START, StateGraph, END

card_builder = StateGraph(CardState)

card_builder.add_node("create", create_card)
card_builder.add_node("search", search_card)
card_builder.add_node("use", use_card)
card_builder.add_node("cancel", cancel_card)
card_builder.add_node("rename", rename_card)
card_builder.add_node("classify_card_action", classify_card_action)
card_builder.add_node("unsupported", unsupported_action)

card_builder.add_edge(START, "classify_card_action")
card_builder.add_conditional_edges(
    "classify_card_action",
    lambda state: state["action"],
)

card_builder.add_edge("create", END)
card_builder.add_edge("search", END)
card_builder.add_edge("use", END)
card_builder.add_edge("cancel", END)
card_builder.add_edge("rename", END)
card_builder.add_edge("unsupported", END)

card_graph = card_builder.compile()
