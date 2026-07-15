import csv
import re
import time
from pathlib import Path

from src.graph.orchestrator import build_graph
from src.models.states import States

# This code reads a CSV file,
# runs each row through your LangGraph pipeline,
# then saves each generated article into a Markdown file.

# Human-readable labels for each pipeline stage, shown while the run is in
# progress. Order must match the graph's node order (planner -> browser ->
# researcher) so progress messages line up with the stream events below.
NODE_LABELS = {
    "planner": "Planning (normalize keywords, choose pattern)",
    "browser": "Browsing (web search for facts)",
    "researcher": "Researching & writing article",
}
NODE_ORDER = list(NODE_LABELS)


def _next_output_counter(output_dir: Path) -> int:
    """
    Find the next free article_N.md number so new runs never overwrite
    articles from a previous run. E.g. if article_1.md exists, the next
    generated file is article_2.md, regardless of the CSV row_id.
    """
    highest = 0
    for existing in output_dir.glob("article_*.md"):
        match = re.fullmatch(r"article_(\d+)\.md", existing.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def main():
    csv_path = Path("keywords.csv")
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    print("Multi-Agent Article Pipeline")
    print(f"Reading rows from {csv_path}...")

    with csv_path.open("r", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))

    total = len(rows)
    print(f"Found {total} row(s) to process.\n")

    # This creates your compiled LangGraph app.
    # app = Planner → Browser → Researcher
    app = build_graph()

    output_counter = _next_output_counter(output_dir)
    succeeded = 0
    failed = 0
    run_start = time.perf_counter()

    for index, row in enumerate(rows, start=1):
        row_id = row["row_id"]
        keywords = row["keywords"]

        print(f"[{index}/{total}] Row {row_id} - keywords: {keywords}")

        state: States = {
            "row": {"row_id": row_id, "keywords": keywords},
            "planner_output": {},
            "browser_output": {},
            "article": "",
            "status": "initialized",
            "error": "",
        }

        row_start = time.perf_counter()
        result = dict(state)
        row_failed = False
        row_error = ""

        next_stage = 0
        if next_stage < len(NODE_ORDER):
            print(f"  -> {NODE_LABELS[NODE_ORDER[next_stage]]}...", end="", flush=True)

        try:
            for chunk in app.stream(state, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    elapsed = time.perf_counter() - row_start
                    result.update(node_output)

                    if node_output.get("status") == "failed":
                        print(f" FAILED ({elapsed:.1f}s)")
                        row_failed = True
                        row_error = node_output.get("error", "unknown error")
                        break

                    print(f" done ({elapsed:.1f}s)")
                    next_stage += 1
                    if next_stage < len(NODE_ORDER):
                        print(
                            f"  -> {NODE_LABELS[NODE_ORDER[next_stage]]}...",
                            end="",
                            flush=True,
                        )
                if row_failed:
                    break
        except Exception as error:
            print(f" FAILED ({time.perf_counter() - row_start:.1f}s)")
            row_failed = True
            row_error = f"unexpected error: {error}"

        if row_failed:
            print(f"  Row {row_id} failed: {row_error}\n")
            failed += 1
            continue

        article = result["article"]
        output_file = output_dir / f"article_{output_counter}.md"
        # Keep the source CSV row traceable even though the filename no
        # longer encodes row_id (that's what caused overwrites before).
        content = f"<!-- source row_id: {row_id} -->\n\n{article}"
        output_file.write_text(content, encoding="utf-8")
        output_counter += 1
        succeeded += 1

        print(f"  Saved: {output_file} ({time.perf_counter() - row_start:.1f}s)\n")

    total_elapsed = time.perf_counter() - run_start
    print(
        f"Done. {succeeded} succeeded, {failed} failed. "
        f"Total time: {total_elapsed:.1f}s"
    )


if __name__ == "__main__":
    main()
