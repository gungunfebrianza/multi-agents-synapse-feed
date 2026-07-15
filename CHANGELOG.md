# Changelog

All notable changes to this project are documented in this file.

## [Unreleased] - 2026-07-15 (5)

### Added

- **"Read the technical detail" link on every card.** Each card now links
  back to the full article it was distilled from. `persist_result`
  (`src/pipeline/runner.py`) now returns the article's numeric id
  alongside its path, and writes `card_N.json` with enough context
  (`row_id`, `keywords`, `pattern`, `card`) to stand alone. New
  `GET /articles/{id}` endpoint (`src/api/app.py`) returns the raw article
  text for that id; the frontend's new `card-detail-button` opens it in a
  glass-panel modal (`frontend/index.html`, `frontend/app.js`,
  `frontend/style.css`) instead of navigating away from the feed.
- **Existing cards from `outputs/` now appear in the feed.** New
  `GET /cards/library` endpoint lists every `outputs/card_*.json` found on
  disk (oldest first) via `list_card_library` (`src/pipeline/runner.py`),
  handling both the current file shape and the older one written before
  this feature existed (a bare card object with no `row_id`/`keywords`/
  `pattern` wrapper — those render with a "no keywords on file" fallback).
  `frontend/app.js`'s `startFeed` now calls this endpoint first and
  renders the whole library before starting live generation for the
  keywords just entered, so the feed opens with real content immediately
  instead of a blank scroll. Verified end-to-end: library listing,
  id-linked article fetch (200 for a real id, 404 for a missing one), and
  a fresh streamed card carrying its own `id` were all tested against a
  running backend.


### Fixed

- **Frontend appeared completely unresponsive after clicking "start
  scrolling."** `frontend/style.css` set an explicit `display: flex` on
  both `.setup-screen` and `.feed-screen`, which silently overrode the
  browser's default `[hidden] { display: none }` behavior (author CSS
  beats the user-agent stylesheet regardless of selector specificity).
  Toggling `.hidden` in `app.js` was therefore a no-op — the request to
  the backend fired and completed correctly (confirmed by generated
  `card_N.json` files), but the screen never visibly changed. Fixed with
  one rule: `[hidden] { display: none !important; }`. Full diagnosis in
  `troubleshoot.md`.

### Added

- **Real per-stage progress via Server-Sent Events.** New
  `POST /cards/stream` endpoint (`src/api/app.py`) streams a `stage` event
  the moment each graph node (planner/browser/researcher/card) finishes,
  instead of one blocking ~30-90s response. Backed by a new
  `run_pipeline_stream` generator in `src/pipeline/runner.py`; the
  existing blocking `run_pipeline` (used by `main.py`) is now a thin
  wrapper around it, so CLI behavior is unchanged. The original
  `POST /cards` endpoint is kept for simple `curl`/script use.
- **Cute, live loading state.** The frontend's loading card now shows an
  animated pulsing/morphing "orb," a real stage label driven by the SSE
  events above (e.g. "Digging through the web for receipts…"), a rotating
  line of playful flavor text so the ~30-90s wait has some personality,
  and a live elapsed-seconds counter — replacing the previous static
  skeleton-line placeholder. (`frontend/app.js`, `frontend/style.css`,
  `frontend/index.html`)
- `troubleshoot.md` — root-cause writeup of the frontend bug above, how it
  was diagnosed, and a general checklist for "backend works, frontend
  doesn't visibly respond" issues.

## [Unreleased] - 2026-07-15

### Fixed

- **Batch job no longer dies on one bad row.** `OpenAIClient.ask()` now
  wraps the underlying agent invocation in a try/except and raises a single,
  catchable `LLMCallError` instead of letting arbitrary provider/network
  exceptions propagate. Each graph node (`planner_node`, `browser_node`,
  `researcher_node`) catches `LLMCallError` (and, where relevant,
  `ValueError` from JSON parsing) and returns `status: "failed"` with an
  `error` message instead of crashing. `main.py` now checks `status` after
  each row and logs+skips failed rows instead of losing the rest of the
  batch. (`src/llm/openai_client.py`, `src/agents/planner.py`,
  `src/agents/browser.py`, `src/agents/researcher.py`, `main.py`)

- **`status` field is now actually used for control flow.** The orchestrator
  previously wrote a `status` field on every node but never read it.
  `build_graph()` now adds conditional edges after `planner` and `browser`
  that route straight to `END` when `status == "failed"`, instead of
  feeding a broken/empty state into the next agent.
  (`src/graph/orchestrator.py`, `src/models/states.py` — added an `error`
  field to `States`)

- **Unsafe positional keyword indexing.** `planner_node` now validates that
  the model returned exactly 3 normalized keywords before returning, and
  `browser_node` re-validates the same invariant before indexing
  `keywords[0..2]` to build its prompt, instead of trusting the shape
  implicitly. A malformed or drifted keyword list now fails the row
  cleanly instead of raising an unhandled `IndexError`/`KeyError`.
  (`src/agents/planner.py`, `src/agents/browser.py`)

- **Indirect prompt injection risk in the Researcher prompt.** Untrusted
  facts retrieved by the Browser agent (from arbitrary live web pages) are
  now wrapped in an explicit `<untrusted_web_facts>...</untrusted_web_facts>`
  delimiter block, and `RESEARCHER_SYSTEM_PROMPT` was hardened with explicit
  rules telling the model to treat that block as inert data and never follow
  instruction-like text found inside it. A best-effort heuristic scan
  (`_flag_suspicious_facts`) also logs a warning when common
  injection-marker phrases show up in Browser facts, for human review. See
  `learn-lesson.md` for the full mechanics and worked examples.
  (`src/agents/researcher.py`)

- **Removed duplicated, unvalidated config path.** `src/config/settings.py`
  was dead code that independently loaded `OPENAI_API_KEY` with no
  validation, diverging from the validated loader actually used in
  `src/llm/openai_client.py`. `settings.py` is now the single source of
  truth (it raises `RuntimeError` if the key is missing, same as before),
  and `OpenAIClient` reads the model name from `settings.OPENAI_MODEL`
  instead of a separate hardcoded default.
  (`src/config/settings.py`, `src/llm/openai_client.py`)

- **Agent graph rebuilt on every LLM call.** `OpenAIClient.ask()` called
  `create_agent(...)` from scratch on every single invocation. It now
  builds each agent once and caches it, keyed by `(system_prompt, tools)`,
  since every call site always passes the same pair. This removes
  avoidable recompilation overhead on every one of the 3 LLM calls per CSV
  row. (`src/llm/openai_client.py`)

- **Planner output template used literal placeholder keys.** The Planner's
  example JSON showed `"A"`/`"B"`/`"C"` as literal dict keys for
  `keyword_rationale` and `research_questions`, risking the model echoing
  those placeholder strings instead of the real keyword text.
  `keyword_rationale` and `research_questions` are now lists of
  `{"keyword": ..., "rationale"/"question": ...}` objects, which removes
  the ambiguity entirely (verified via a live end-to-end run that the
  model now returns real keyword text in both fields).
  (`src/agents/planner.py`)

### Added

- `README.md` documenting the architecture, setup, and how to run the
  project.
- `learn-lesson.md` — an educational write-up on how prompt injection can
  attack this multi-agent pipeline specifically, with worked examples.

## [Unreleased] - 2026-07-15 (2)

### Fixed

- **Output files were silently overwritten on every run.** `main.py` named
  articles `article_{row_id}.md`, so re-running the pipeline against the
  same `keywords.csv` replaced every previous result. It now scans
  `outputs/` for the highest existing `article_N.md` number at startup and
  continues from `N + 1` for every article written during the run (e.g. if
  `article_1.md` exists, the next generated file is `article_2.md`),
  regardless of CSV `row_id`. The originating `row_id` is preserved as an
  HTML comment on the first line of each generated file for traceability.
  (`main.py`)

### Added

- **Live, per-stage progress output for `main.py`.** Running
  `python main.py` previously printed nothing until each row's article was
  fully written. It now uses the compiled graph's `stream(...,
  stream_mode="updates")` API to print a row counter (`[2/5] Row 3 -
  keywords: ...`), a label and elapsed time for each pipeline stage as it
  completes (Planning / Browsing / Researching), a per-row failure message
  if a stage fails, and a final summary line (`N succeeded, N failed,
  total time`). (`main.py`)

## [Unreleased] - 2026-07-15 (3)

### Added

- **Card agent (`src/agents/card.py`, new `card` graph node).** Converts
  the Researcher's article + Browser's facts into a single JSON card —
  `hook`, `why_it_matters`, `action`, `action_effort` (`15min | 1hr |
  weekend`) — following the exact editorial rules specified (checkable
  hook, no filler, second-person `why_it_matters` honestly tied to a
  reader project or a learning-goal fallback, exactly one startable
  action, no fabrication, no hype/emoji). Wired in as
  `researcher -> card -> END` in `src/graph/orchestrator.py`; `States`
  gained a `card` field. Reuses the same untrusted-data delimiting as the
  Researcher fix for the facts it consumes.
- **Shared pipeline runner (`src/pipeline/runner.py`).** Extracted the
  "stream the graph and merge state" logic and the output-persistence
  logic out of `main.py` so both the CLI and the new API call the same
  code (`run_pipeline`, `persist_result`). `persist_result` is now
  thread-locked to stay collision-safe under concurrent API requests.
  `main.py` was refactored to use this module; behavior for CSV batch runs
  is unchanged other than also writing `card_N.json` alongside each
  `article_N.md` when a card was generated.
- **FastAPI backend (`src/api/app.py`).** `POST /cards` takes exactly 3
  client-supplied keywords (no more reading from `keywords.csv` for this
  path), runs the full graph for that one request, persists the result,
  and returns the card as JSON (HTTP 502 with the error message on
  pipeline failure). `GET /health` for liveness. CORS wide open for local
  frontend development. Verified end-to-end with a live request (see
  `outputs/article_6.md` / `outputs/card_6.json`, generated during
  testing).
- **Doomscroll frontend (`frontend/index.html`, `style.css`, `app.js`).**
  Static, no build step. Setup screen collects 3 keywords (category
  picker shows research/coding/finance/business, only "research" enabled
  per the current scope). Feed screen renders cards fetched from the
  backend with scroll-snap, a one-card-ahead prefetch so scrolling doesn't
  feel like "tap and wait," a skeleton loading card, and a retry-capable
  error card. Dark, glassmorphism, `Space Grotesk` / `JetBrains Mono`
  theme.
- `requirements.txt` — pinned versions for all now-explicit dependencies
  (`langgraph`, `langchain`, `langchain-openai`, `python-dotenv`,
  `fastapi`, `uvicorn[standard]`, `pydantic`).
- `tutorial.md` — file-by-file walkthrough of how the card agent, backend,
  and frontend were built, and a "where to look when tracing a change"
  table.
