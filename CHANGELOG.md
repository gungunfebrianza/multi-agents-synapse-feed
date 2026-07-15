# Changelog

All notable changes to this project are documented in this file.

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
