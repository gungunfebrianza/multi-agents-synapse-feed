import csv
from pathlib import Path

from src.graph.orchestrator import build_graph
from src.models.states import States

# This code reads a CSV file,
# runs each row through your LangGraph pipeline,
# then saves each generated article into a Markdown file.

def main():
    csv_path = Path("keywords.csv")
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    # This creates your compiled LangGraph app.
    # app = Planner → Browser → Researcher
    app = build_graph()

    with csv_path.open("r", encoding="utf-8") as file:
        # This reads each CSV row as a dictionary.
        reader = csv.DictReader(file)

        # If your CSV has 3 rows, the graph runs 3 times.
        for row in reader:
            # This creates the starting state for one article.
            state: States = {
                "row": {
                    "row_id": row["row_id"],
                    "keywords": row["keywords"],
                },
                "planner_output": {},
                "browser_output": {},
                "article": "",
                "status": "initialized",
                "error": "",
            }

            # This sends the state into LangGraph. A failure on this row is
            # isolated here so the rest of the batch still runs.
            try:
                result = app.invoke(state)
            except Exception as error:
                print(f"FAILED row_id={row['row_id']}: unexpected error: {error}")
                continue

            if result.get("status") == "failed":
                print(f"FAILED row_id={row['row_id']}: {result.get('error')}")
                continue

            row_id = result["planner_output"]["row_id"]
            article = result["article"]

            # This writes the article text into the Markdown file.
            output_file = output_dir / f"article_{row_id}.md"
            output_file.write_text(article, encoding="utf-8")

            print(f"Generated: {output_file}")


if __name__ == "__main__":
    main()
