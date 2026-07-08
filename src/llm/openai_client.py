import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY is missing. Add it to your .env file.")


class OpenAIClient:
    def __init__(self, model: str = "gpt-5.4"):
        self.llm = ChatOpenAI(
            model=model,
            use_responses_api=True,
        )

    def ask(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[Any] | None = None,
    ) -> str:
        """
        Run one agent call and return the final text response.
        """

        agent = create_agent(
            model=self.llm,
            tools=tools or [],
            system_prompt=system_prompt,
        )

        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": user_prompt,
                    }
                ]
            }
        )

        final_message = result["messages"][-1]
        return self._extract_text(final_message)

    def ask_json(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run one agent call and parse the final response as JSON.
        """

        text = self.ask(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tools=tools,
        )

        return self._parse_json(text)

    def _extract_text(self, message: Any) -> str:
        """
        Handles normal AIMessage.content and Responses API content blocks.
        """

        if hasattr(message, "text") and message.text:
            return message.text

        content = getattr(message, "content", "")

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            text_parts: list[str] = []

            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)

                elif isinstance(block, dict):
                    if block.get("type") == "text" and "text" in block:
                        text_parts.append(block["text"])
                    elif "text" in block:
                        text_parts.append(block["text"])

            return "\n".join(text_parts).strip()

        return str(content)

    def _parse_json(self, text: str) -> dict[str, Any]:
        """
        Parses strict JSON. Also cleans accidental ```json fences.
        """

        cleaned = text.strip()

        cleaned = re.sub(r"^```json\s*", "", cleaned)
        cleaned = re.sub(r"^```\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Model did not return valid JSON.\n\nRaw output:\n{cleaned}"
            ) from error
        