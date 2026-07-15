import csv
import time
from pathlib import Path

from src.graph.orchestrator import build_graph
from src.pipeline.runner import NODE_LABELS, NODE_ORDER, persist_result, run_pipeline

# This code reads a CSV file,
# runs each row through your LangGraph pipeline,
# then saves each generated article (and its action card) into outputs/.


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
    # app = Planner → Browser → Researcher → Card
    app = build_graph()

    succeeded = 0
    failed = 0
    run_start = time.perf_counter()
    run_start_labels_printed = {"stage": 0}

    for index, row in enumerate(rows, start=1):
        row_id = row["row_id"]
        keywords = row["keywords"]

        print(f"[{index}/{total}] Row {row_id} - keywords: {keywords}")

        run_start_labels_printed["stage"] = 0
        print(f"  -> {NODE_LABELS[NODE_ORDER[0]]}...", end="", flush=True)

        def on_stage(node_name, node_output, elapsed):
            if node_output.get("status") == "failed":
                print(f" FAILED ({elapsed:.1f}s)")
                return

            print(f" done ({elapsed:.1f}s)")
            run_start_labels_printed["stage"] += 1
            next_index = run_start_labels_printed["stage"]
            if next_index < len(NODE_ORDER):
                print(
                    f"  -> {NODE_LABELS[NODE_ORDER[next_index]]}...",
                    end="",
                    flush=True,
                )

        try:
            result = run_pipeline(app, row_id, keywords, on_stage=on_stage)
        except Exception as error:
            print(" FAILED")
            print(f"  Row {row_id} failed: unexpected error: {error}\n")
            failed += 1
            continue

        if result.get("status") == "failed":
            print(f"  Row {row_id} failed: {result.get('error')}\n")
            failed += 1
            continue

        article_path, card_id = persist_result(output_dir, row_id, result)
        succeeded += 1
        print(f"  Saved: {article_path} (id {card_id})\n")

    total_elapsed = time.perf_counter() - run_start
    print(
        f"Done. {succeeded} succeeded, {failed} failed. "
        f"Total time: {total_elapsed:.1f}s"
    )


if __name__ == "__main__":
    main()
