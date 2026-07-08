from langgraph.graph import END, START, StateGraph

# This code builds your LangGraph workflow.
# START → planner → browser → researcher → END
#This imports your three agent functions
from src.agents.browser import browser_node
from src.agents.planner import planner_node
from src.agents.researcher import researcher_node

# This imports your state schema.
from src.models.states import States

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
    # After planner finishes, run browser.
    graph.add_edge("planner", "browser")
    # After browser finishes, run researcher.
    graph.add_edge("browser", "researcher")
    # After researcher finishes, stop the workflow.
    graph.add_edge("researcher", END)

    return graph.compile()