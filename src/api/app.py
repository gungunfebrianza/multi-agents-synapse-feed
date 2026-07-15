import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from src.graph.orchestrator import build_graph
from src.pipeline.runner import (
    list_card_library,
    persist_result,
    run_pipeline,
    run_pipeline_stream,
)

OUTPUT_DIR = Path("outputs")

app = FastAPI(title="Synapse Feed API")

# Local demo: the frontend is a static page opened from a different
# origin/port than this API, so allow any origin rather than hardcoding
# one. Do not carry this wildcard into a deployment with real users/auth.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# The compiled graph has no per-request state, so build it once at import
# time and reuse it (and its cached OpenAIClient agents) across requests.
_graph = build_graph()


class CardRequest(BaseModel):
    keywords: list[str] = Field(
        ..., min_length=3, max_length=3, description="Exactly 3 keywords."
    )

    @field_validator("keywords")
    @classmethod
    def _keywords_non_empty(cls, keywords: list[str]) -> list[str]:
        cleaned = [keyword.strip() for keyword in keywords]
        if any(not keyword for keyword in cleaned):
            raise ValueError("Each keyword must be a non-empty string.")
        return cleaned


class CardResponse(BaseModel):
    id: int | None = None
    row_id: str
    keywords: list[str]
    pattern: str | None = None
    card: dict
    status: str
    error: str = ""


class LibraryResponse(BaseModel):
    cards: list[CardResponse]


class ArticleResponse(BaseModel):
    id: int
    content: str


def _build_payload(
    row_id: str,
    fallback_keywords: list[str],
    result: dict[str, Any],
    card_id: int | None = None,
) -> dict:
    planner_output = result.get("planner_output", {})
    return {
        "id": card_id,
        "row_id": row_id,
        "keywords": planner_output.get("keywords", fallback_keywords),
        "pattern": planner_output.get("pattern"),
        "card": result.get("card", {}),
        "status": result.get("status", "unknown"),
        "error": result.get("error", ""),
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/cards/library", response_model=LibraryResponse)
def get_card_library() -> LibraryResponse:
    """
    List every previously generated card (from outputs/card_*.json,
    written by this API or by `python main.py`), oldest first, so the
    frontend can show the existing library before generating anything new.
    """
    entries = list_card_library(OUTPUT_DIR)
    return LibraryResponse(
        cards=[
            CardResponse(
                id=entry["id"],
                row_id=entry["row_id"],
                keywords=entry["keywords"],
                pattern=entry["pattern"],
                card=entry["card"],
                status="completed",
            )
            for entry in entries
        ]
    )


@app.get("/articles/{article_id}", response_model=ArticleResponse)
def get_article(article_id: int) -> ArticleResponse:
    """
    Return the full article behind a given card id — the "read the
    technical detail" link on a card fetches this.
    """
    path = OUTPUT_DIR / f"article_{article_id}.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"article_{article_id}.md not found")

    return ArticleResponse(id=article_id, content=path.read_text(encoding="utf-8"))


@app.post("/cards", response_model=CardResponse)
def generate_card(request: CardRequest) -> CardResponse:
    """
    Run the full Planner -> Browser -> Researcher -> Card pipeline for the
    3 keywords the client supplied, and return the resulting card in one
    blocking response. Each call is a fresh LLM run (no caching), so the
    same keywords produce a different card every time.

    This is a slow, blocking call (~30-90s: it does live web search plus
    4 sequential LLM calls) with no progress feedback until it's done —
    prefer POST /cards/stream from a browser so the UI can show real
    per-stage progress instead of a blank wait.
    """
    row_id = f"api-{uuid.uuid4().hex[:8]}"
    keywords_str = ", ".join(request.keywords)

    result = run_pipeline(_graph, row_id, keywords_str)

    if result.get("status") == "failed":
        raise HTTPException(
            status_code=502,
            detail=result.get("error", "pipeline failed for an unknown reason"),
        )

    # Persist alongside the CLI's outputs/ so both entry points share one
    # audit trail (article_N.md + card_N.json).
    _article_path, card_id = persist_result(OUTPUT_DIR, row_id, result)

    return CardResponse(**_build_payload(row_id, request.keywords, result, card_id))


@app.post("/cards/stream")
def generate_card_stream(request: CardRequest) -> StreamingResponse:
    """
    Same pipeline as POST /cards, but streamed as Server-Sent Events so the
    client can show real progress instead of a single 30-90s blocking wait.

    Emits one "stage" event per completed graph node:
      event: stage
      data: {"stage": "planner", "status": "planned", "elapsed": 7.5}

    then one final "done" event carrying the same payload POST /cards
    returns (or a "failed" status/error if the pipeline failed):
      event: done
      data: {"id": 13, "row_id": ..., "card": {...}, "status": "completed", ...}
    """
    row_id = f"api-{uuid.uuid4().hex[:8]}"
    keywords_str = ", ".join(request.keywords)

    def event_stream():
        for node_name, node_output, elapsed in run_pipeline_stream(
            _graph, row_id, keywords_str
        ):
            if node_name == "__done__":
                result = node_output
                card_id = None
                if result.get("status") != "failed":
                    _article_path, card_id = persist_result(OUTPUT_DIR, row_id, result)
                payload = _build_payload(row_id, request.keywords, result, card_id)
                yield f"event: done\ndata: {json.dumps(payload)}\n\n"
                return

            stage_payload = {
                "stage": node_name,
                "status": node_output.get("status"),
                "elapsed": round(elapsed, 1),
            }
            yield f"event: stage\ndata: {json.dumps(stage_payload)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Disables response buffering on nginx-style proxies; harmless
            # for local/direct uvicorn use.
            "X-Accel-Buffering": "no",
        },
    )
