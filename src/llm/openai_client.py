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
        # Store the model inside this class so other methods can use it.
        self.llm = ChatOpenAI(
            model=model,
            # Use OpenAI's newer Responses API mode.
            use_responses_api=True,
        )

    # This method sends a prompt to the agent and returns text.
    def ask(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[Any] | None = None,
    ) -> str:
        """
        Run one agent call and return the final text response.
        """
        # This creates an agent.
        agent = create_agent(
            model=self.llm,
            # If tools is provided, use it. If tools is None, use empty list [].
            tools=tools or [],
            system_prompt=system_prompt,
        )

        # This runs the agent.
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

        # the last message is the final answer from the AI.
        final_message = result["messages"][-1]
        # This extracts clean text from that final AI message.
        return self._extract_text(final_message)

    # This is like ask(), but it expects the model to return JSON.
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

    # This method takes an AI message and returns plain text.
    # Because LangChain/OpenAI responses can come in different shapes.
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

    # This method converts model text into Python JSON/dict.
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
        