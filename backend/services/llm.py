"""Generic LLM abstraction so the provider/model can be swapped in one place.

To add a new provider: implement BaseLLMClient, add one branch to get_llm_client().
Nothing else in the codebase needs to change.
"""
import os
from abc import ABC, abstractmethod

from dotenv import load_dotenv

load_dotenv()


class BaseLLMClient(ABC):
    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        """Return the raw text content of the model's response."""
        raise NotImplementedError


class GroqLLMClient(BaseLLMClient):
    def __init__(self, model: str, api_key: str):
        from groq import Groq

        self._client = Groq(api_key=api_key)
        self._model = model

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        json_mode: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_completion_tokens=max_tokens,
            # gpt-oss/qwen reasoning models leak <think> chains into content
            # unless reasoning is explicitly excluded. Never use reasoning_format.
            include_reasoning=False,
            **kwargs,
        )
        return response.choices[0].message.content.strip()


def get_llm_client() -> BaseLLMClient:
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    model = os.getenv("LLM_MODEL", "qwen/qwen3-32b")

    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        return GroqLLMClient(model=model, api_key=api_key)

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
