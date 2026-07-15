# This imports your custom class that talks to OpenAI/LangChain.
from src.llm.openai_client import LLMCallError, OpenAIClient

# This creates one reusable OpenAI client.
openai_client = OpenAIClient()

# This tells the AI what role it should play.
PLANNER_SYSTEM_PROMPT = """
ROLE: You are the PLANNER agent.

You set up one article's recombination task.

Your job:
1. Normalize the input into exactly 3 load-bearing keywords.
2. Choose one recombination pattern.
3. Write 3 current research questions for the Browser agent.

Rules:
- Output valid strict JSON only.
- Do not include markdown.
- Do not include explanations outside JSON.
- The JSON must match the requested structure exactly.
- Every placeholder in the JSON structure below must be replaced with the
  real keyword text. Never output the literal placeholder strings
  themselves (e.g. do not output "<keyword_1>").
"""

# This is a LangGraph node.
# START → planner_node → browser_node → researcher_node → END
def planner_node(state):
    # The state is the shared data dictionary passed through the whole graph.
    row = state["row"]

    row_id = row["row_id"]
    keywords = row["keywords"]
    # This creates the actual task for the Planner agent.
    user_prompt = f"""
INPUT CSV ROW:
row_id: {row_id}
keywords: {keywords}

TASK:
1. NORMALIZE to exactly 3 load-bearing keywords:
   - If 3 keywords given, use as-is.
   - If 2 given, add ONE adjacent keyword that creates productive tension.
   - If 1 given, add TWO keywords from different domains to force cross-domain recombination.
   - Record WHY each added keyword was chosen.
   - If a keyword was given, write "given" as its rationale.

2. SELECT ONE recombination pattern best suited to these keywords:
   [
     "Triadic Fusion",
     "Cross-Domain Transfer",
     "Constraint Collision",
     "Inversion",
     "Failure-Mode Mining",
     "Adversarial Recombination"
   ]

3. WRITE 3 research questions the Browser must answer — one per keyword.
   Each question must target CURRENT, factual, buildable detail.
   Do not ask for basic definitions.

OUTPUT JSON ONLY:
{{
  "row_id": "{row_id}",
  "keywords": ["<keyword_1>", "<keyword_2>", "<keyword_3>"],
  "keyword_rationale": [
    {{"keyword": "<keyword_1>", "rationale": "..."}},
    {{"keyword": "<keyword_2>", "rationale": "..."}},
    {{"keyword": "<keyword_3>", "rationale": "..."}}
  ],
  "pattern": "...",
  "pattern_reason": "...",
  "research_questions": [
    {{"keyword": "<keyword_1>", "question": "..."}},
    {{"keyword": "<keyword_2>", "question": "..."}},
    {{"keyword": "<keyword_3>", "question": "..."}}
  ]
}}
"""
    # This sends the prompt to the OpenAI client and gets back JSON.
    # This sends both prompts to the model.
    try:
        planner_output = openai_client.ask_json(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        normalized_keywords = planner_output.get("keywords")
        if not isinstance(normalized_keywords, list) or len(normalized_keywords) != 3:
            raise ValueError(
                "Planner must return exactly 3 normalized keywords, got: "
                f"{normalized_keywords!r}"
            )
    except (LLMCallError, ValueError) as error:
        # Isolate the failure to this row instead of crashing the whole batch.
        return {
            "planner_output": {},
            "status": "failed",
            "error": f"planner_node: {error}",
        }

    return {
        "planner_output": planner_output,
        "status": "planned",
        "error": "",
    }
