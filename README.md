# multi-agents-synapse-feed

A four-agent LangGraph pipeline that turns 3 keywords into a single,
sourced "recombination" article plus a short, checkable action card. It can
be run two ways:

- **Batch, from a CSV** (`main.py`) — one row per article, written to `outputs/`.
- **On demand, from a web UI** (`frontend/` + `src/api/app.py`) — a visitor
  types 3 keywords into a doomscroll-style feed, which opens with every
  card already generated so far and then keeps generating brand-new ones
  as they scroll, via the FastAPI backend.

Each agent is a thin wrapper around a single OpenAI call (via LangChain's
`create_agent`), wired together as nodes in a LangGraph graph.

## Architecture

### Agents (`src/agents/`)

- **`planner.py` — `planner_node`**
  Reads `state["row"]` (`row_id`, `keywords`). Prompts the model to:
  1. Normalize the input into exactly 3 "load-bearing" keywords (adding related keywords with a stated rationale if fewer than 3 were given).
  2. Select one recombination pattern (e.g. "Triadic Fusion", "Constraint Collision", "Inversion", ...).
  3. Write one current, factual research question per keyword for the Browser agent.
  Returns strict JSON as `planner_output`, and sets `status = "planned"`. Fails the row (`status = "failed"`) instead of raising if the model doesn't return exactly 3 keywords.

- **`browser.py` — `browser_node`**
  Reads `planner_output` (keywords, research questions). Calls the model with a `web_search` tool bound to it and instructs it to only retrieve and report facts — never synthesize or combine keywords. Returns 3-5 sourced facts (with `fact`, `source`, `confidence`) per keyword as strict JSON in `browser_output`, and sets `status = "browsed"`.

- **`researcher.py` — `researcher_node`**
  Reads `planner_output` (keywords, pattern, pattern_reason) and `browser_output` (facts). Prompts the model to apply the chosen recombination pattern, ground every technical claim in a provided fact, state one non-hedged thesis, prove interdependence of the three keywords (what breaks if each is removed), note an adversarial failure mode, and end with an open research question. Returns the final article text as `article`, and sets `status = "completed"`. The Browser's facts are untrusted web content, so they're passed to the model inside a delimited `<untrusted_web_facts>` block with explicit instructions not to follow anything instruction-like found inside it — see `learn-lesson.md` for why.

- **`card.py` — `card_node`**
  Reads the finished `article` and the Browser's `facts` ("grounding material"). Prompts the model to compress them into one JSON card — `hook`, `why_it_matters`, `action`, `action_effort` (`15min | 1hr | weekend`) — meant to nudge the reader toward exactly one concrete, startable next step, grounded only in the material above (no fabricated claims, no "explore more" filler). Sets `status = "completed"`.

Each agent module creates its own module-level `OpenAIClient` instance and defines a fixed system prompt describing the agent's role and rules. Any node can fail a row (setting `status = "failed"` and `error`) instead of crashing the whole run; see `src/graph/orchestrator.py`.

### Orchestration (`src/graph/orchestrator.py`)

`build_graph()` builds a `StateGraph(States)`:

```
START -> planner -> browser -> researcher -> card -> END
```

with a conditional edge after each of the first three nodes: if a node set `status = "failed"`, the graph skips straight to `END` instead of feeding a broken state into the next agent.

### State (`src/models/states.py`)

| field            | type             | set by      | purpose                                                        |
|------------------|------------------|-------------|-----------------------------------------------------------------|
| `row`            | `dict[str, Any]` | caller      | the input row (`row_id`, `keywords`)                             |
| `planner_output` | `dict[str, Any]` | planner     | normalized keywords, rationale, chosen pattern, research questions |
| `browser_output` | `dict[str, Any]` | browser     | sourced facts per keyword                                       |
| `article`        | `str`            | researcher  | the final generated article text                                |
| `card`           | `dict[str, Any]` | card        | `hook` / `why_it_matters` / `action` / `action_effort`           |
| `status`         | `str`            | every node  | `initialized` -> `planned` -> `browsed` -> `completed`, or `failed` |
| `error`          | `str`            | any node    | set alongside `status = "failed"`                                |

### Pipeline runner (`src/pipeline/runner.py`)

Shared by both entry points:

- `run_pipeline_stream(app, row_id, keywords)` streams the graph node-by-node, yielding `(node_name, node_output, elapsed_seconds)` per stage; `run_pipeline(...)` is a blocking wrapper around it for callers (like `main.py`) that just want the final result, optionally observing progress via `on_stage=...`.
- `persist_result(output_dir, row_id, result)` writes `article_N.md` (+ `card_N.json`, containing `row_id`/`keywords`/`pattern`/`card`, if a card exists) using the next free `N`, so repeat runs never overwrite previous output. Returns `(article_path, N)`.
- `list_card_library(output_dir)` reads every `card_*.json` in `output_dir` back into `{id, row_id, keywords, pattern, card}` entries (oldest first), used to repopulate the frontend feed with previously generated cards.

### LLM client (`src/llm/openai_client.py`)

`OpenAIClient` wraps `langchain_openai.ChatOpenAI` (model from `settings.OPENAI_MODEL`, Responses API) behind a LangChain `create_agent` call, cached per `(system_prompt, tools)` pair so the agent graph isn't recompiled on every call:

- `ask(system_prompt, user_prompt, tools=None)` runs one agent turn and returns the final response as plain text. Wraps failures in `LLMCallError`.
- `ask_json(system_prompt, user_prompt, tools=None)` calls `ask` and parses the result as strict JSON, stripping accidental ```` ```json ```` fences. Raises `ValueError` if the model output isn't valid JSON.

Only the Browser agent passes `tools=[{"type": "web_search"}]`.

### Settings (`src/config/settings.py`)

The single source of truth for config: loads `.env` and exposes `settings.OPENAI_API_KEY` / `settings.OPENAI_MODEL`. Raises `RuntimeError` at import time if `OPENAI_API_KEY` is missing.

## Setup

### Requirements

- Python 3.x (a `.venv` virtual environment is included in this repo)
- An OpenAI API key with access to the configured model and web search tool use

### Dependencies

```bash
pip install -r requirements.txt
```

### Environment variables

Create a `.env` file in the project root:

```
OPENAI_API_KEY="sk-..."
```

Without it, importing `OpenAIClient` (directly or via `settings`) raises `RuntimeError: OPENAI_API_KEY is missing. Add it to your .env file.`

## Running

### Batch run over a CSV (`main.py`)

Reads `keywords.csv` (columns: `row_id`, `keywords`), runs the full graph once per row with live progress output, and writes each result to `outputs/`:

```bash
python main.py
```

### Web UI: backend + frontend

```bash
uvicorn src.api.app:app --host 127.0.0.1 --port 8000   # backend
cd frontend && python -m http.server 5500               # frontend, separate terminal
```

Open `http://127.0.0.1:5500/`, enter 3 keywords, and scroll. The feed first loads every card already in `outputs/` (`GET /cards/library`), then keeps generating new ones as you scroll via `POST /cards/stream` (Server-Sent Events — live per-stage progress while you wait). Every card has a "read the technical detail" link that fetches its full article from `GET /articles/{id}`. Full build notes: see `tutorial.md`; if the UI ever looks unresponsive, see `troubleshoot.md`.

### Single ad-hoc run (`main_min.py`)

Runs the graph once against a hardcoded `row` (edit the `state` dict in the file to change the input) and prints planner/browser output and the final article to stdout:

```bash
python main_min.py
```

### Standalone web-search check (`websearch.py`)

A small script unrelated to the graph that sanity-checks the `web_search` tool binding directly against `ChatOpenAI`:

```bash
python websearch.py
```

## Output

- **Batch mode**: `outputs/article_<N>.md` (+ `outputs/card_<N>.json` if the card stage succeeded), where `N` auto-increments across runs so nothing gets overwritten. The originating `row_id` is kept as an HTML comment on the article's first line.
- **API mode**: the same files are written server-side for traceability. `card_<N>.json` (`row_id`, `keywords`, `pattern`, `card`) is returned directly in the HTTP response too, tagged with its `id` (`N`); the full article behind any card is fetchable at `GET /articles/<id>`, and every previously generated card is listable at `GET /cards/library`.

Article format: `Title` / `Thesis` / `The System` / `Interdependence proof` / `Failure mode` / `Open question`, with technical claims inline-cited to Browser-gathered sources.

## Further reading

- `tutorial.md` — how the Card agent, FastAPI backend, and frontend were built, file-by-file.
- `learn-lesson.md` — how prompt injection can attack this pipeline via the Browser → Researcher/Card boundary, and the mitigations in place.
- `troubleshoot.md` — a worked debugging example (frontend looked unresponsive despite the backend working) and a general checklist for similar issues.
- `CHANGELOG.md` — dated log of fixes and features.
