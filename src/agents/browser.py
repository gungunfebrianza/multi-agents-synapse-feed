from src.llm.openai_client import OpenAIClient

openai_client = OpenAIClient()

# This code is the fact-gathering agent, it reads the Planner’s keywords/questions, 
# uses web search to collect sourced facts, 
# converts them into JSON, and saves them into LangGraph state for the Researcher agent.
# This is the role instruction for the Browser agent.
BROWSER_SYSTEM_PROMPT = """
ROLE: You are the BROWSER agent.

You gather raw, current, factual material.

You do NOT synthesize.
You do NOT combine keywords.
You do NOT invent facts.
You only retrieve and report.

Rules:
- Use web search for current information.
- Return 3 to 5 concrete facts per keyword.
- Prefer numbers, dates, versions, mechanisms, named techniques, official docs, papers, and primary sources.
- Every fact must include a source URL or source name.
- If uncertain, mark confidence as "low".
- Output valid strict JSON only.
- Do not include markdown.
"""
# this system prompt controls the behavior of the Browser agent.

# This is a LangGraph node.
# LangGraph will call this function after the Planner finishes.
def browser_node(state):
    # This takes the previous agent’s result.
    planner_output = state["planner_output"]

    row_id = planner_output["row_id"]
    keywords = planner_output["keywords"]
    research_questions = planner_output["research_questions"]

    # This creates the actual task sent to the model.
    user_prompt = f"""
INPUT:
row_id: {row_id}
keywords: {keywords}
research_questions: {research_questions}

TASK:
For EACH keyword, answer its research question using retrieved web sources.

Return 3 to 5 concrete facts per keyword.

OUTPUT JSON ONLY:
{{
  "row_id": "{row_id}",
  "facts": {{
    "{keywords[0]}": [
      {{
        "fact": "...",
        "source": "...",
        "confidence": "high"
      }}
    ],
    "{keywords[1]}": [
      {{
        "fact": "...",
        "source": "...",
        "confidence": "high"
      }}
    ],
    "{keywords[2]}": [
      {{
        "fact": "...",
        "source": "...",
        "confidence": "high"
      }}
    ]
  }}
}}
"""
    # This is important because the next agent, Researcher, needs predictable data.
    # The Researcher does not want random text. It wants structured facts.

    # This is the most important part, allows the model to search the internet.
    # Without this tool, the model would only use its internal knowledge.
    # With this tool, the Browser can find current facts.
    browser_output = openai_client.ask_json(
        system_prompt=BROWSER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tools=[
            {"type": "web_search"}
        ],
    )

    # This sends new data back to LangGraph.
    # LangGraph merges this into the global state.
    return {
        "browser_output": browser_output,
        "status": "browsed",
    }