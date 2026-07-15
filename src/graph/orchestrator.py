from langgraph.graph import END, START, StateGraph

# This code builds your LangGraph workflow.
# START → planner → browser → researcher → END
# (planner/browser can short-circuit straight to END on failure — see
# _route_on_status below)
#This imports your three agent functions
from src.agents.browser import browser_node
from src.agents.planner import planner_node
from src.agents.researcher import researcher_node

# This imports your state schema.
from src.models.states import States


def _route_on_status(state: States) -> str:
    """
    Shared conditional-edge router: if a node marked the run as "failed",
    skip straight to END instead of feeding a broken/empty state into the
    next agent.
    """
    return "end" if state.get("status") == "failed" else "continue"


# This defines a function that creates and returns your workflow.
def build_graph():
    # This creates a new graph.
    graph = StateGraph(States)

    # This adds the first agent to the graph.
    # Nodes are the agents.
    graph.add_node("planner", planner_node)
    graph.add_node("browser", browser_node)
    graph.add_node("researcher", researcher_node)

    # Edges are the arrows between agents.
    # When the graph starts, run planner first.
    graph.add_edge(START, "planner")
    # After planner finishes, run browser — unless planner failed.
    graph.add_conditional_edges(
        "planner", _route_on_status, {"continue": "browser", "end": END}
    )
    # After browser finishes, run researcher — unless browser failed.
    graph.add_conditional_edges(
        "browser", _route_on_status, {"continue": "researcher", "end": END}
    )
    # After researcher finishes (success or failure), stop the workflow.
    graph.add_edge("researcher", END)

    # This converts your graph definition into a runnable app.
    return graph.compile()
