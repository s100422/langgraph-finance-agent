from .nodes import MainState
from .nodes import classify_category,account_wrapper,product_wrapper,bill_payment_wrapper,card_wrapper,unsupported_category
from langgraph.graph import START, StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

main_graph_builder = StateGraph(MainState)

main_graph_builder.add_node("classify_category", classify_category)
main_graph_builder.add_node("account", account_wrapper)
main_graph_builder.add_node("product", product_wrapper)
main_graph_builder.add_node("card", card_wrapper)
main_graph_builder.add_node("bill_payment", bill_payment_wrapper)
main_graph_builder.add_node("unsupported", unsupported_category)

main_graph_builder.add_edge(START, "classify_category")
main_graph_builder.add_conditional_edges(
    "classify_category",
    lambda state: state["category"],
)

main_graph_builder.add_edge("account", END)
main_graph_builder.add_edge("product", END)
main_graph_builder.add_edge("card", END)
main_graph_builder.add_edge("bill_payment", END)
main_graph_builder.add_edge("unsupported", END)

main_graph = main_graph_builder.compile(MemorySaver())
