from src.llm.openai_client import OpenAIClient

openai_client = OpenAIClient()

# This is the identity and behavior instruction for the Researcher agent.
RESEARCHER_SYSTEM_PROMPT = """
ROLE: You are the RESEARCHER agent.

You recombine three keywords into ONE novel, buildable idea, then write the article.

Rules:
- Use ONLY the facts provided by the Browser.
- Do not invent new facts.
- You may invent new ideas.
- Every technical claim must be grounded in a provided fact.
- Cite facts inline using the source field from the Browser output.
- No hedging.
- No filler.
- Every keyword must be structurally essential.
"""

# This function is one LangGraph node.
# LangGraph will call it after the Browser node finishes.
def researcher_node(state):
    # This takes previous results from the shared LangGraph state.
    planner_output = state["planner_output"]
    browser_output = state["browser_output"]

    # This pulls out the exact data the Researcher needs.
    keywords = planner_output["keywords"]
    pattern = planner_output["pattern"]
    pattern_reason = planner_output["pattern_reason"]
    facts = browser_output["facts"]

# This creates the actual task message sent to the model.
    user_prompt = f"""
INPUT:
keywords: {keywords}
pattern: {pattern}
pattern_reason: {pattern_reason}
facts: {facts}

TASK:
Apply the assigned recombination pattern.

1. Force all three keywords into ONE system where each is load-bearing.
2. If pattern is "Constraint Collision":
   - impose keyword A's hardest constraint onto keyword B
   - show what keyword C must become to satisfy both
3. Ground every technical claim in the provided facts.
4. Make ONE strong, non-hedged thesis.
5. Prove interdependence:
   - what breaks if keyword A is removed
   - what breaks if keyword B is removed
   - what breaks if keyword C is removed
6. Give an adversarial failure check in 2 lines.
7. End with one open research question.

OUTPUT ARTICLE FORMAT:

Title: ...

Thesis:
...

The System:
...

Interdependence proof:
- Remove {keywords[0]}: ...
- Remove {keywords[1]}: ...
- Remove {keywords[2]}: ...

Failure mode:
...

Open question:
...
"""
# Dynamic keyword names in the output format
# This means the prompt will automatically insert the actual keywords.

    article = openai_client.ask(
        system_prompt=RESEARCHER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
    )

    return {
        "article": article,
        "status": "completed",
    }