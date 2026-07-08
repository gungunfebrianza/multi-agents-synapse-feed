from langgraph.graph import END, START, StateGraph

from src.agents.browser import browser_node
from src.agents.planner import planner_node
from src.agents.researcher import researcher_node
from src.models.states import States


def build_graph():
    graph = StateGraph(States)

    graph.add_node("planner", planner_node)
    graph.add_node("browser", browser_node)
    graph.add_node("researcher", researcher_node)

    graph.add_edge(START, "planner")
    graph.add_edge("planner", "browser")
    graph.add_edge("browser", "researcher")
    graph.add_edge("researcher", END)

    return graph.compile()