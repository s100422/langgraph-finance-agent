from .nodes import subscribe_product, search_product, terminate_product, apply_loan, rename_product, classify_product_action, unsupported_action
from .nodes import ProductState
from langgraph.graph import START, StateGraph, END

product_builder = StateGraph(ProductState)

product_builder.add_node("subscribe", subscribe_product)
product_builder.add_node("search", search_product)
product_builder.add_node("terminate", terminate_product)
product_builder.add_node("apply_loan", apply_loan)
product_builder.add_node("rename", rename_product)
product_builder.add_node("classify_product_action", classify_product_action)
product_builder.add_node("unsupported", unsupported_action)

product_builder.add_edge(START, "classify_product_action")
product_builder.add_conditional_edges(
    "classify_product_action",
    lambda state: state["action"],
)

product_builder.add_edge("subscribe", END)
product_builder.add_edge("search", END)
product_builder.add_edge("terminate", END)
product_builder.add_edge("apply_loan", END)
product_builder.add_edge("rename", END)
product_builder.add_edge("unsupported", END)

product_graph = product_builder.compile()
