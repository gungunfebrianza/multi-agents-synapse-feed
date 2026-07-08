from src.llm.openai_client import OpenAIClient

openai_client = OpenAIClient()


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


def browser_node(state):
    planner_output = state["planner_output"]

    row_id = planner_output["row_id"]
    keywords = planner_output["keywords"]
    research_questions = planner_output["research_questions"]

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

    browser_output = openai_client.ask_json(
        system_prompt=BROWSER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tools=[
            {"type": "web_search"}
        ],
    )

    return {
        "browser_output": browser_output,
        "status": "browsed",
    }