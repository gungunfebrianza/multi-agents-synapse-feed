from typing import Any, TypedDict

class States(TypedDict):
    row: dict[str, Any]
    planner_output: dict[str, Any]
    browser_output: dict[str, Any]
    article: str
    card: dict[str, Any]
    status: str
    error: str
