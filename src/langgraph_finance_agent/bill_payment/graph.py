from .nodes import (
    register_bill_payment, search_bill_payment, terminate_bill_payment, rename_bill_payment,
    classify_bill_payment_action, unsupported_action,
)
from .nodes import BillPaymentState
from langgraph.graph import START, StateGraph, END

bill_payment_builder = StateGraph(BillPaymentState)

bill_payment_builder.add_node("register", register_bill_payment)
bill_payment_builder.add_node("search", search_bill_payment)
bill_payment_builder.add_node("terminate", terminate_bill_payment)
bill_payment_builder.add_node("rename", rename_bill_payment)
bill_payment_builder.add_node("classify_bill_payment_action", classify_bill_payment_action)
bill_payment_builder.add_node("unsupported", unsupported_action)

bill_payment_builder.add_edge(START, "classify_bill_payment_action")
bill_payment_builder.add_conditional_edges(
    "classify_bill_payment_action",
    lambda state: state["action"],
)

bill_payment_builder.add_edge("register", END)
bill_payment_builder.add_edge("search", END)
bill_payment_builder.add_edge("terminate", END)
bill_payment_builder.add_edge("rename", END)
bill_payment_builder.add_edge("unsupported", END)

bill_payment_graph = bill_payment_builder.compile()
