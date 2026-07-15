# multi-agents-synapse-feed

A three-agent LangGraph pipeline that turns a small set of keywords into a single, sourced, "recombination" article. For each row of an input CSV (a `row_id` and a comma-separated `keywords` string), the system normalizes the keywords, plans a synthesis pattern, gathers current facts from the web for each keyword, and then writes an article that forces all keywords into one interdependent idea, grounding every technical claim in a cited fact.

Each agent is a thin wrapper around a single OpenAI call (via LangChain's `create_agent`), and the three agents are wired together as nodes in a linear LangGraph graph. Generated articles are written to `outputs/article_<row_id>.md`.

## Architecture

### Agents (`src/agents/`)

- **`planner.py` — `planner_node`**
  Reads `state["row"]` (`row_id`, `keywords`). Prompts the model to:
  1. Normalize the input into exactly 3 "load-bearing" keywords (adding related keywords with a stated rationale if fewer than 3 were given).
  2. Select one recombination pattern (e.g. "Triadic Fusion", "Constraint Collision", "Inversion", ...).
  3. Write one current, factual research question per keyword for the Browser agent.
  Returns strict JSON as `planner_output`, and sets `status = "planned"`.

- **`browser.py` — `browser_node`**
  Reads `planner_output` (keywords, research questions). Calls the model with a `web_search` tool bound to it and instructs it to only retrieve and report facts — never synthesize or combine keywords. Returns 3-5 sourced facts (with `fact`, `source`, `confidence`) per keyword as strict JSON in `browser_output`, and sets `status = "browsed"`.

- **`researcher.py` — `researcher_node`**
  Reads `planner_output` (keywords, pattern, pattern_reason) and `browser_output` (facts). Prompts the model to apply the chosen recombination pattern, ground every technical claim in a provided fact, state one non-hedged thesis, prove interdependence of the three keywords (what breaks if each is removed), note an adversarial failure mode, and end with an open research question. Returns the final article text as `article`, and sets `status = "completed"`.

Each agent module creates its own module-level `OpenAIClient` instance and defines a fixed system prompt describing the agent's role and rules.

### Orchestration (`src/graph/orchestrator.py`)

`build_graph()` builds a `StateGraph(States)` and wires the nodes into a fixed, linear flow with no branching or looping:

```
START -> planner -> browser -> researcher -> END
```

The compiled graph is invoked once per CSV row; LangGraph merges each node's return dict into the shared state before passing it to the next node.

### State (`src/models/states.py`)

`States` is a `TypedDict` shared across every node in the graph:

| field            | type             | set by      | purpose                                                        |
|------------------|------------------|-------------|-----------------------------------------------------------------|
| `row`            | `dict[str, Any]` | caller      | the input CSV row (`row_id`, `keywords`)                        |
| `planner_output` | `dict[str, Any]` | planner     | normalized keywords, rationale, chosen pattern, research questions |
| `browser_output` | `dict[str, Any]` | browser     | sourced facts per keyword                                       |
| `article`        | `str`            | researcher  | the final generated article text                                |
| `status`         | `str`            | every node  | pipeline progress marker (`initialized` -> `planned` -> `browsed` -> `completed`) |

### LLM client (`src/llm/openai_client.py`)

`OpenAIClient` wraps `langchain_openai.ChatOpenAI` (model `gpt-5.4`, Responses API) behind a LangChain `create_agent` call:

- `ask(system_prompt, user_prompt, tools=None)` runs one agent turn and returns the final response as plain text, handling both plain-string and Responses-API content-block message shapes.
- `ask_json(system_prompt, user_prompt, tools=None)` calls `ask` and parses the result as strict JSON, stripping accidental ```` ```json ```` fences. Raises `ValueError` if the model output isn't valid JSON.

The Browser agent is the only one that passes `tools=[{"type": "web_search"}]`, giving it live web search; Planner and Researcher only use the model's own reasoning over the data already in state.

The client raises `RuntimeError` at import time if `OPENAI_API_KEY` is not set.

### Settings (`src/config/settings.py`)

A minimal `Settings` class that loads `.env` and exposes `OPENAI_API_KEY` as `settings.OPENAI_API_KEY`. (Note: `src/llm/openai_client.py` reads `OPENAI_API_KEY` directly via `os.getenv` rather than importing this class.)

## Setup

### Requirements

- Python 3.x (a `.venv` virtual environment is included in this repo)
- An OpenAI API key with access to the `gpt-5.4` model and web search tool use

### Dependencies

There is no `requirements.txt` or `pyproject.toml` in this repo; install the packages the code imports directly:

```bash
pip install langgraph langchain langchain-openai python-dotenv
```

### Environment variables

Create a `.env` file in the project root:

```
OPENAI_API_KEY="sk-..."
```

This is loaded by `python-dotenv` in both `src/llm/openai_client.py` and `src/config/settings.py`. Without it, importing `OpenAIClient` raises `RuntimeError: OPENAI_API_KEY is missing. Add it to your .env file.`

## Running

### Batch run over a CSV (`main.py`)

Reads `keywords.csv` (columns: `row_id`, `keywords`), runs the full graph once per row, and writes each result to `outputs/article_<row_id>.md`:

```bash
python main.py
```

Example `keywords.csv` row: `1,python` or `3,"openai agent, solidity, payment"`.

### Single ad-hoc run (`main_min.py`)

Runs the graph once against a hardcoded `row` (edit the `state` dict in the file to change the input) and prints the planner output, browser output, and final article to stdout instead of writing a file:

```bash
python main_min.py
```

### Standalone web-search check (`websearch.py`)

A small script unrelated to the graph that sanity-checks the `web_search` tool binding directly against `ChatOpenAI`:

```bash
python websearch.py
```

## Output

Generated articles are written as Markdown files to `outputs/`, one per CSV row, named `article_<row_id>.md`. Each article follows the format produced by the Researcher agent's prompt:

- `Title`
- `Thesis`
- `The System`
- `Interdependence proof` (what breaks if each of the 3 keywords is removed)
- `Failure mode`
- `Open question`

Technical claims in the article are inline-cited to the sources gathered by the Browser agent (e.g. `[Microsoft Learn: 'IoT Edge supported platforms']`).
