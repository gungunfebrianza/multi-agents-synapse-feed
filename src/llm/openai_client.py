import json
import re
from typing import Any

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from src.config.settings import settings


class LLMCallError(Exception):
    """Raised when a call to the underlying LLM/agent fails (network, API, timeout, etc.)."""


class OpenAIClient:
    def __init__(self, model: str | None = None):
        # Store the model inside this class so other methods can use it.
        self.llm = ChatOpenAI(
            model=model or settings.OPENAI_MODEL,
            # Use OpenAI's newer Responses API mode.
            use_responses_api=True,
        )

        # Agent graphs are expensive to compile. Every call site always uses
        # the same (system_prompt, tools) pair, so cache and reuse them
        # instead of rebuilding on every ask()/ask_json() call.
        self._agent_cache: dict[tuple[str, tuple[str, ...]], Any] = {}

    def _get_agent(self, system_prompt: str, tools: list[Any] | None) -> Any:
        tools = tools or []
        tool_signature = tuple(json.dumps(tool, sort_keys=True) for tool in tools)
        cache_key = (system_prompt, tool_signature)

        if cache_key not in self._agent_cache:
            self._agent_cache[cache_key] = create_agent(
                model=self.llm,
                tools=tools,
                system_prompt=system_prompt,
            )

        return self._agent_cache[cache_key]

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
        agent = self._get_agent(system_prompt, tools)

        try:
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
        except Exception as error:
            # Network errors, rate limits, auth failures, etc. all land here.
            # Surface them as one clear, catchable type instead of letting an
            # arbitrary provider/library exception crash the whole pipeline.
            raise LLMCallError(f"LLM call failed: {error}") from error

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
