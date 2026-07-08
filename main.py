import csv
from pathlib import Path

from src.graph.orchestrator import build_graph
from src.models.states import States


def main():
    csv_path = Path("keywords.csv")
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    app = build_graph()

    with csv_path.open("r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            state: States = {
                "row": {
                    "row_id": row["row_id"],
                    "keywords": row["keywords"],
                },
                "planner_output": {},
                "browser_output": {},
                "article": "",
                "status": "initialized",
            }

            result = app.invoke(state)

            row_id = result["planner_output"]["row_id"]
            article = result["article"]

            output_file = output_dir / f"article_{row_id}.md"
            output_file.write_text(article, encoding="utf-8")

            print(f"Generated: {output_file}")


if __name__ == "__main__":
    main()