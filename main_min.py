from src.graph.orchestrator import build_graph
from src.models.states import States


def main():
    state: States = {
        "row": {
            "row_id": 2,
            "keywords": "distributed systems, zero-knowledge proof",
        },
        "planner_output": {},
        "browser_output": {},
        "article": "",
        "status": "initialized",
        "error": "",
    }

    app = build_graph()
    result = app.invoke(state)

    if result.get("status") == "failed":
        print(f"FAILED: {result.get('error')}")
        return

    print("\n=== PLANNER OUTPUT ===")
    print(result["planner_output"])

    print("\n=== BROWSER OUTPUT ===")
    print(result["browser_output"])

    print("\n=== FINAL ARTICLE ===")
    print(result["article"])


if __name__ == "__main__":
    main()
