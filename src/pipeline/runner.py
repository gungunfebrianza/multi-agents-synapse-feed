import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator

from src.models.states import States

# Human-readable labels for each pipeline stage, in graph order. Shared by
# the CLI (main.py) and the API (src/api/app.py) so progress reporting and
# the graph's actual node order never drift apart.
NODE_LABELS = {
    "planner": "Planning (normalize keywords, choose pattern)",
    "browser": "Browsing (web search for facts)",
    "researcher": "Researching & writing article",
    "card": "Building action card",
}
NODE_ORDER = list(NODE_LABELS)

OnStage = Callable[[str, dict[str, Any], float], None]

# Guards the output-counter scan + write so concurrent callers (e.g.
# multiple API requests) can't race each other into picking the same
# article_N.md number.
_output_lock = threading.Lock()


def run_pipeline_stream(
    app,
    row_id: str,
    keywords: str,
) -> Iterator[tuple[str, dict[str, Any], float]]:
    """
    Run the full graph for one (row_id, keywords) pair, yielding
    (node_name, node_output, elapsed_seconds) as each stage completes.

    The final item always has node_name == "__done__" and node_output set
    to the full merged result dict (check result["status"] == "failed" and
    result["error"] there for pipeline failures — this generator does not
    raise for node-level failures, only for infrastructure errors from
    app.stream itself).
    """
    state: States = {
        "row": {"row_id": row_id, "keywords": keywords},
        "planner_output": {},
        "browser_output": {},
        "article": "",
        "card": {},
        "status": "initialized",
        "error": "",
    }

    result: dict[str, Any] = dict(state)
    start = time.perf_counter()

    for chunk in app.stream(state, stream_mode="updates"):
        for node_name, node_output in chunk.items():
            elapsed = time.perf_counter() - start
            result.update(node_output)
            yield node_name, node_output, elapsed

            if node_output.get("status") == "failed":
                yield "__done__", result, elapsed
                return

    yield "__done__", result, time.perf_counter() - start


def run_pipeline(
    app,
    row_id: str,
    keywords: str,
    on_stage: OnStage | None = None,
) -> dict[str, Any]:
    """
    Blocking convenience wrapper around run_pipeline_stream for callers
    that just want the final result (optionally observing progress via
    on_stage(node_name, node_output, elapsed_seconds) as each stage
    completes).
    """
    result: dict[str, Any] = {}

    for node_name, node_output, elapsed in run_pipeline_stream(app, row_id, keywords):
        if node_name == "__done__":
            result = node_output
            break
        if on_stage:
            on_stage(node_name, node_output, elapsed)

    return result


def next_output_counter(output_dir: Path) -> int:
    """
    Find the next free article_N.md number so new runs never overwrite
    articles from a previous run. E.g. if article_1.md exists, the next
    generated file is article_2.md.
    """
    highest = 0
    for existing in output_dir.glob("article_*.md"):
        match = re.fullmatch(r"article_(\d+)\.md", existing.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def list_card_library(output_dir: Path) -> list[dict[str, Any]]:
    """
    Read every card_N.json in output_dir and return them as a list of
    {id, row_id, keywords, pattern, card} dicts, sorted by id ascending
    (oldest first).

    Handles two on-disk shapes: the current one (this whole dict, written
    by persist_result) and the legacy one from before this function
    existed, where card_N.json held only the card's own 4 fields
    (hook/why_it_matters/action/action_effort) with no wrapper — those are
    still readable, just with empty keywords/pattern.
    """
    entries: list[dict[str, Any]] = []

    for path in output_dir.glob("card_*.json"):
        match = re.fullmatch(r"card_(\d+)\.json", path.name)
        if not match:
            continue

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        card_id = int(match.group(1))

        if isinstance(raw, dict) and isinstance(raw.get("card"), dict):
            entries.append(
                {
                    "id": card_id,
                    "row_id": raw.get("row_id", ""),
                    "keywords": raw.get("keywords", []),
                    "pattern": raw.get("pattern"),
                    "card": raw["card"],
                }
            )
        elif isinstance(raw, dict):
            # Legacy shape: the file *is* the card object.
            entries.append(
                {
                    "id": card_id,
                    "row_id": "",
                    "keywords": [],
                    "pattern": None,
                    "card": raw,
                }
            )

    entries.sort(key=lambda entry: entry["id"])
    return entries


def persist_result(output_dir: Path, row_id: str, result: dict[str, Any]) -> tuple[Path, int]:
    """
    Write the article (and card, if present) to outputs/ under the next
    free counter, and return (article_path, counter). Thread-safe so
    concurrent API requests don't collide on the same filename.

    card_N.json is written with enough context (row_id, keywords, pattern)
    to be re-rendered as a full card later without re-reading article_N.md
    — see GET /cards/library in src/api/app.py.
    """
    output_dir.mkdir(exist_ok=True)

    with _output_lock:
        counter = next_output_counter(output_dir)

        article_path = output_dir / f"article_{counter}.md"
        content = f"<!-- source row_id: {row_id} -->\n\n{result.get('article', '')}"
        article_path.write_text(content, encoding="utf-8")

        card = result.get("card")
        if card:
            planner_output = result.get("planner_output", {})
            card_payload = {
                "row_id": row_id,
                "keywords": planner_output.get("keywords", []),
                "pattern": planner_output.get("pattern"),
                "card": card,
            }
            card_path = output_dir / f"card_{counter}.json"
            card_path.write_text(json.dumps(card_payload, indent=2), encoding="utf-8")

    return article_path, counter
