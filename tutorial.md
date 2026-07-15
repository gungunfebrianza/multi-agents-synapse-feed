# Tutorial: How the Backend and Frontend Were Built

This documents the Card agent, the FastAPI backend, and the doomscroll
frontend added on top of the existing Planner → Browser → Researcher
pipeline, so future changes can be traced back to why each piece exists.

## 1. What changed, in one picture

```
BEFORE:
  keywords.csv -> planner -> browser -> researcher -> outputs/article_N.md

AFTER:
  keywords.csv -> planner -> browser -> researcher -> card -> outputs/article_N.md + card_N.json
  (main.py, batch mode)                                  |
                                                          |
  3 client keywords -> [same graph, one row] -------------+
  (FastAPI /cards, one request = one row)                 |
                                                          v
                                            frontend (doomscroll feed) renders the card
```

The graph itself gained one node (`card`). Everything downstream of that —
the API and the frontend — exists to get keywords in and a card out over
HTTP instead of a CSV file.

## 2. The Card agent (`src/agents/card.py`)

A fourth LangGraph node, run after `researcher`. It does not call the web;
it takes the Researcher's finished article plus the Browser's raw facts
("grounding material") and asks the LLM to compress them into one JSON
card: `hook`, `why_it_matters`, `action`, `action_effort`.

The system prompt encodes the exact rules that were specified for this
feature (specific/checkable hook, no filler, second-person
`why_it_matters` tied to a real reader project *or* honestly falls back to
a learning goal, exactly one startable action, effort capped to
`15min | 1hr | weekend`, no fabrication, no hype). `card_node` validates
the response has all four fields and that `action_effort` is one of the
three allowed values, failing the row (not raising) if not — same pattern
as the other three nodes.

`reader_projects` is read from `state["row"]` if present but is not
currently populated anywhere (no reader-profile system exists yet), so in
practice `why_it_matters` always falls back to a learning-goal connection.
If you later add real reader-project input, plumb it into
`state["row"]["reader_projects"]` and this node picks it up with no other
changes.

Because the Browser's facts are untrusted web content (see
`learn-lesson.md`), `card_node` reuses the same defense pattern as
`researcher.py`: facts are wrapped in `<untrusted_web_facts>` tags with an
explicit instruction not to treat their contents as commands.

**Graph wiring** (`src/graph/orchestrator.py`): `researcher` now routes to
`card` via the same `_route_on_status` conditional edge used elsewhere
(skip straight to `END` if the Researcher failed), and `card` is the new
terminal node before `END`.

**State** (`src/models/states.py`): added a `card: dict[str, Any]` field.

## 3. Shared pipeline runner (`src/pipeline/runner.py`)

Before this change, `main.py` owned all the logic for streaming the graph
node-by-node and printing progress. The API needed the exact same
"run the graph for one row" logic, so it was extracted here:

- `run_pipeline(app, row_id, keywords, on_stage=None)` — runs
  `app.stream(state, stream_mode="updates")`, merges each node's partial
  output into a result dict, and optionally calls `on_stage(node_name,
  node_output, elapsed_seconds)` after each stage. `main.py` passes a
  callback that prints progress; the API passes nothing (it just wants the
  final result).
- `next_output_counter(output_dir)` / `persist_result(output_dir, row_id,
  result)` — the article/card file-writing + collision-avoidance logic
  (see the "no overwrite" changelog entry). `persist_result` is
  thread-locked because the API can serve concurrent requests and both
  requests scanning `outputs/` for "the next free number" at the same time
  would otherwise be a race.

`main.py` and `src/api/app.py` both import from this module. If you need
to change how a row is run or how output files are named, change it once,
here.

## 4. Backend (`src/api/app.py`)

A single-file FastAPI app:

- `GET /health` — liveness check, returns `{"status": "ok"}`.
- `POST /cards` — body `{"keywords": [k1, k2, k3]}` (Pydantic enforces
  exactly 3 non-empty strings). Runs `run_pipeline` for one synthetic row
  (`row_id` is a random `api-<hex>` id, keywords joined into the same
  comma-separated string format the CSV path already used), persists the
  result via `persist_result`, and returns:
  ```json
  {
    "row_id": "api-97b1b6a1",
    "keywords": ["...", "...", "..."],
    "pattern": "Constraint Collision",
    "card": { "hook": "...", "why_it_matters": "...", "action": "...", "action_effort": "15min" },
    "status": "completed",
    "error": ""
  }
  ```
  On a pipeline failure it returns HTTP 502 with the error message instead
  of a fake/empty card. This endpoint blocks for the full ~30-90s with no
  progress feedback — kept for simple `curl`/script use, but the frontend
  does not use it.
- `POST /cards/stream` — same request body, same pipeline, but streamed as
  Server-Sent Events (`text/event-stream`) via `run_pipeline_stream`
  (`src/pipeline/runner.py`) so the client gets a real event the moment
  each graph node finishes, instead of one blocking response at the end:
  ```
  event: stage
  data: {"stage": "planner", "status": "planned", "elapsed": 5.0}

  event: stage
  data: {"stage": "browser", "status": "browsed", "elapsed": 27.3}

  event: stage
  data: {"stage": "researcher", "status": "completed", "elapsed": 42.3}

  event: stage
  data: {"stage": "card", "status": "completed", "elapsed": 45.0}

  event: done
  data: { "row_id": "...", "keywords": [...], "pattern": "...", "card": {...}, "status": "completed", "error": "" }
  ```
  The frontend is the intended client for this endpoint — see §5.

**Why this is safe to call from the browser directly**: the graph is built
once at import time (`_graph = build_graph()`) and reused; `OpenAIClient`
already caches its LangChain agents internally (see the earlier efficiency
fix), so repeated requests don't re-pay agent-compile cost. The endpoint
function is a normal (non-`async def`) function, so FastAPI runs it in a
worker thread automatically — a slow, blocking pipeline call doesn't
freeze the whole server for other requests.

**CORS**: wide open (`allow_origins=["*"]`) because the frontend is a
static page served from a different origin/port than the API during local
development, and there's no auth/session model to protect. Tighten this
before putting the API anywhere other than your own machine.

**Run it**:
```bash
pip install -r requirements.txt
uvicorn src.api.app:app --host 127.0.0.1 --port 8000
```
(Use a different `--port` if 8000 is already taken on your machine —
check with `netstat -ano | findstr :8000` on Windows first.)

Interactive API docs are auto-generated at `http://127.0.0.1:8000/docs`.

## 5. Frontend (`frontend/`)

Plain HTML/CSS/JS, no build step, no framework.

- `index.html` — two screens in one page, toggled by hiding/showing:
  a **setup screen** (category pills — only "research" is enabled, the
  other three are visibly present but disabled with a "soon" tag, per the
  personalization requirement — and 3 keyword text inputs), and a
  **feed screen** (sticky header + scrollable card feed). `<template>`
  elements define the markup for a real card, a loading card, and an error
  card, so `app.js` never builds HTML with string concatenation.
- `style.css` — the "gloomy" look: a near-black gradient background with
  two soft violet/red radial glows, a very faint animated-noise overlay,
  and glassmorphism panels (`backdrop-filter: blur(...)` + translucent
  `rgba` fills + hairline borders) for the setup card and every feed card.
  Typography is `Space Grotesk` (display) + `JetBrains Mono` (labels,
  metadata, code-like bits) loaded from Google Fonts, with a system-font
  fallback stack if that fails to load. Each feed card is
  `scroll-snap-align: start` inside a `scroll-snap-type: y mandatory`
  container, so scrolling snaps card-to-card like a reels/shorts feed
  instead of stopping mid-card.

  **`[hidden] { display: none !important; }`** is declared near the top of
  this file. Without it, the `.setup-screen`/`.feed-screen` classes'
  explicit `display: flex` silently overrides the browser's default
  `[hidden]` behavior (author CSS beats the user-agent stylesheet
  regardless of selector specificity) and toggling `.hidden` in JS has no
  visible effect at all. This exact bug shipped once already — see
  `troubleshoot.md` for the full diagnosis. Keep this rule if you add more
  `hidden`-toggled screens/panels.
- `app.js` — all the behavior:
  1. On form submit, validates 3 non-empty keywords and calls
     `startFeed(keywords)`.
  2. `startFeed` clears the feed, appends an invisible 1px **sentinel**
     div at the end, and loads the first card via `appendNextCard()`.
  3. `appendNextCard()` inserts a loading card just before the sentinel,
     awaits a card (a prefetched one if already in flight, otherwise
     starts a fresh fetch), swaps the loading card for the real card (or
     an error card with a retry button) — then immediately starts
     fetching the *next* card in the background and stores that promise.
     This is the "always one card generating ahead" trick: because
     generation genuinely takes tens of seconds, without this the feed
     would feel like "tap, wait a minute, tap again" instead of
     doomscrolling.
  4. An `IntersectionObserver` watches the sentinel with a generous
     `rootMargin` (800px), so `appendNextCard()` fires *before* the user
     physically reaches the bottom, not after.
  5. Cards are generated by calling `POST /cards/stream` and reading the
     response body as a stream (`response.body.getReader()`), parsing
     Server-Sent Event frames by hand (`parseSseEvent`) rather than using
     the native `EventSource` (which only supports `GET`, and this needs
     to `POST` the keywords). `streamCard(onStage)` resolves once the
     `done` event arrives; `fetchCardSafe()` wraps it so it always
     resolves to `{ok, data}` or `{ok: false, error}` and never rejects —
     this keeps `appendNextCard` free of try/catch and avoids
     unhandled-promise-rejection noise from the background prefetch.
  6. **The loading card is a live progress display, not a static
     skeleton**: `renderLoadingCard()` returns an element with an
     animated CSS "orb" (a morphing/pulsing blob), a stage label
     (`el._setStage(name)`, updated in real time from each `stage` SSE
     event via `STAGE_LABELS`), a rotating flavor-text line
     (`FLAVOR_TEXTS`, cycled on a `setInterval` for personality during the
     longer stages), and a live elapsed-seconds counter. Only the *first*
     card fetched for a given loading card gets live stage updates — a
     card already being prefetched in the background had no visible
     loading element to update when it started, so it falls back to the
     generic orb + counter (documented in a comment in `appendNextCard`).
     `el._stopTimers()` must be called before the loading element is
     discarded, or its intervals keep ticking on a detached DOM node.
  7. The API base URL defaults to `http://127.0.0.1:8000` and can be
     overridden with `?api=http://host:port` in the page URL — useful if
     you run the backend on a different port because 8000 was taken.

**Run it** (any static file server works; Python's built-in one is enough
for local use):
```bash
cd frontend
python -m http.server 5500
```
Then open `http://127.0.0.1:5500/` with the backend already running.

**Known trade-off**: this is a from-scratch demo feed, not a production
infinite-scroll implementation. It prefetches exactly one card ahead (not
a deep buffer), there's no client-side caching or offline support, and a
slow/failed backend shows up as a visible loading or error card rather
than being hidden — that's intentional for a "here's really what's
happening" demo, but worth knowing if you extend it.

## 6. Where to look when tracing a future change

| You want to change...                                   | Edit...                                  |
|-----------------------------------------------------------|-------------------------------------------|
| The card's JSON shape or writing rules                    | `src/agents/card.py`                       |
| Which nodes run, or their order                            | `src/graph/orchestrator.py`, `src/models/states.py` |
| How a single row is executed / progress reporting          | `src/pipeline/runner.py`                   |
| CSV batch behavior (CLI)                                   | `main.py`                                  |
| API request/response shape, validation, endpoints          | `src/api/app.py`                           |
| Card layout, colors, fonts, snap-scroll behavior            | `frontend/style.css`                       |
| Feed structure, loading/error states, keyword form          | `frontend/index.html`                      |
| Prefetch/scroll logic, API calls from the browser            | `frontend/app.js`                          |
| Streaming/progress protocol between backend and frontend      | `src/api/app.py` (`/cards/stream`), `frontend/app.js` (`streamCard`) |

See also `troubleshoot.md` for a worked debugging example (why the feed
appeared to do nothing after clicking "start scrolling") and a general
checklist for "backend works, frontend doesn't visibly respond" bugs.
| Pinned dependency versions                                  | `requirements.txt`                         |
